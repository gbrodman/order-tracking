import asyncio
import collections
import csv
import datetime
import email
import os
import re
import sys
import time
import traceback
from imaplib import IMAP4_SSL
from typing import Any, Tuple, Dict, List, Iterable

import aiohttp
import requests
from bs4 import BeautifulSoup, Tag
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support.ui import Select
from tqdm import tqdm

import lib.email_auth as email_auth
from lib import util, email_tracking_retriever
from lib.archive_manager import ArchiveManager
from lib.tracking import Tracking

LOGIN_EMAIL_FIELD = "fldEmail"
LOGIN_PASSWORD_FIELD = "fldPassword"
LOGIN_BUTTON_SELECTOR = "//button[contains(text(), 'Login')]"

SUBMIT_BUTTON_SELECTOR = "//*[contains(text(), 'SUBMIT')]"

RESULT_SELECTOR = "//*[contains(text(), 'record(s) effected')]"
RESULT_REGEX = r"(\d+) record\(s\) effected"

BASE_URL_FORMAT = "https://%s.com"
MANAGEMENT_URL_FORMAT = "https://www.%s.com/p/it@orders-all/"

RECEIPTS_URL_FORMAT = "https://%s.com/p/it@receipts"
MELUL_EXPORTS_FOLDER = os.path.join(os.getcwd(), 'exports')
EXPORT_WAIT_TIMEOUT_SECONDS = 60

DTMD_URL = "https://gibstrat.com"
OAKS_URL = "http://hso-tech.com"
EMB_URL = "http://embdeals.com"

USA_LOGIN_URL = "https://usabuying.group/login"
USA_TRACKING_URL = "https://usabuying.group/trackings"
USA_PO_URL = "https://usabuying.group/purchase-orders"

USA_API_LOGIN_URL = "https://api.usabuying.group/index.php/buyers/login"
USA_API_TRACKINGS_URL = "https://api.usabuying.group/index.php/buyers/trackings"

YRCW_URL = "https://app.yrcwtech.com/"

MAX_UPLOAD_ATTEMPTS = 10

TrackingInfo = Tuple[str, float, str]
TrackingTuple = Tuple[str]
TrackingInfoDict = Dict[TrackingTuple, TrackingInfo]

PoCostDict = Dict[str, float]
ReconResult = Tuple[TrackingInfoDict, PoCostDict]


def fill_busted_bfmr_costs(result: TrackingInfoDict, table: Tag, date: str):
  trs = table.find_all('tr')
  # busted-ass html doesn't close the <tr> tags until the end
  tds = trs[1].find_all('td')
  # shave out the "total amount" tds
  tds = tds[:-2]

  for i in range(len(tds) // 5):
    tracking = tds[i * 5].getText().upper().strip()
    total_text = tds[i * 5 + 4].getText()
    total = float(total_text.replace(',', '').replace('$', ''))
    previous_total = result[(tracking,)][1] if (tracking,) in result else 0.0
    result[(tracking,)] = ('bfmr', previous_total + total, date)


def fill_standard_bfmr_costs(result: TrackingInfoDict, table: Tag, date: str):
  rows = table.find_all('tr')[1:]  # skip the header
  for row in rows:
    tds = row.find_all('td')
    if len(tds) != 5:
      continue
    tracking = tds[0].getText().upper().strip()
    total = float(tds[4].getText().strip().replace(',', '').replace('$', ''))
    previous_total = result[(tracking,)][1] if (tracking,) in result else 0.0
    result[(tracking,)] = ('bfmr', previous_total + total, date)


def add_bfmr_cost_if_nonempty(result: TrackingInfoDict, tracking: str, cost: float, date: str):
  if cost:
    previous_total = result[(tracking,)][1] if (tracking,) in result else 0.0
    result[(tracking,)] = ('bfmr', previous_total + cost, date)


def fill_2020_12_22_bfmr_costs(result: TrackingInfoDict, table: Tag, date: str):
  rows = table.find_all('tr')[1:]
  tracking = rows[0].text.strip()
  if '$' in tracking:  # old format, we can quit
    return
  cost_for_tracking = 0.0
  for row in rows[1:-1]:  # skip the first (we have the tracking) and the last (total amount)
    if '$' in row.text:
      match = re.search(r'\$([0-9,.]+)', row.text)
      if not match:
        raise Exception(f"Unknown BFMR format, found row {row.text} but expected a cost")
      cost_for_tracking += float(match.group(1))
    else:
      add_bfmr_cost_if_nonempty(result, tracking, cost_for_tracking, date)
      cost_for_tracking = 0.0
      tracking = row.text.strip()
  # cover the last tracking (fence post)
  add_bfmr_cost_if_nonempty(result, tracking, cost_for_tracking, date)


def clean_csv_tracking(tracking: str) -> str:
  return re.sub(r'[^0-9A-Z,]', '', tracking.upper())


def _delete_existing_exports():
  if not os.path.exists(MELUL_EXPORTS_FOLDER):
    os.mkdir(MELUL_EXPORTS_FOLDER)

  for filename in os.listdir(MELUL_EXPORTS_FOLDER):
    os.remove(f"{MELUL_EXPORTS_FOLDER}/{filename}")


class GroupSiteManager:

  def __init__(self, config, driver_creator) -> None:
    self.config = config
    self.driver_creator = driver_creator
    self.melul_portal_groups = config['melulPortals']
    self.archive_manager = ArchiveManager(config)

  def upload(self, trackings: Iterable[Tracking]) -> None:
    groups_dict: Dict[str, List[Tracking]] = collections.defaultdict(list)
    for tracking in trackings:
      groups_dict[tracking.group].append(tracking)

    for group, trackings in groups_dict.items():
      numbers = [tracking.tracking_number for tracking in trackings]
      group_config = self.config['groups'][group]
      if group_config.get('password') and group_config.get('username'):
        self._upload_to_group(numbers, group)

  def get_new_tracking_pos_costs_maps_with_retry(self, group: str) -> ReconResult:
    last_exc = None
    for i in range(5):
      try:
        return self.get_new_tracking_pos_costs_maps(group)
      except Exception as e:
        print(f"Received exception when getting costs: {str(e)}\n{util.get_traceback_lines()}\n"
              "Retrying up to five times.")
        last_exc = e
    raise Exception("Exceeded retry limit", last_exc)

  def get_new_tracking_pos_costs_maps(self, group: str) -> ReconResult:
    if group == 'bfmr':
      print("Loading BFMR emails")
      return self._get_bfmr_costs(), {}
    elif group in self.melul_portal_groups:
      group_config = self.config['groups'][group]
      username = group_config['username']
      password = group_config['password']
      trackings_info, po_cost = self._melul_get_tracking_pos_costs_maps(group, username, password)

      if 'archives' in group_config:
        for archive_group in group_config['archives']:
          print(f"Loading archive {archive_group}")
          if not self.archive_manager.has_archive(archive_group):
            archive_trackings_info, archive_po_cost = self._melul_get_tracking_pos_costs_maps(
                archive_group, username, password)
            self.archive_manager.put_archive(archive_group, archive_po_cost, archive_trackings_info)

          archive_po_cost, archive_trackings_info = self.archive_manager.get_archive(archive_group)
          po_cost.update(archive_po_cost)
          trackings_info.update(archive_trackings_info)

      return trackings_info, po_cost
    elif group == "usa":
      print("Loading group usa")
      return asyncio.run(self._get_usa_tracking_pos_prices())
    elif group == "yrcw":
      print("Loading yrcw")
      return self._get_yrcw_tracking_pos_prices()
    elif group == "oaks":
      return self._get_oaks_tracking_pos_prices()
    return dict(), dict()

  def _get_oaks_tracking_pos_prices(self) -> ReconResult:
    tracking_infos: Dict[Tuple[str], Tuple[str, float, str]] = {}
    driver = self._login_oaks()
    try:
      with tqdm(desc=f"Fetching oaks check-ins", unit='page') as pbar:
        elem = driver.find_element_by_id('ContentPlaceHolder1_ddlReportes')
        elem.click()
        select = Select(elem)
        select.select_by_visible_text('Resume')
        time.sleep(15)  # the site can be super slow

        while True:
          table = driver.find_elements_by_tag_name('table')[-1]
          rows = table.find_elements_by_tag_name('tr')
          for row in rows:
            tds = row.find_elements_by_tag_name('td')
            if len(tds) < 6:
              continue
            tracking = tds[1].text.upper().strip()
            if not tracking or tracking.startswith("TRACKING"):
              continue
            cost = tds[5].text.replace('$', '').replace(',', '').replace('-', '').strip()
            cost_value = float(cost) if cost else 0.0
            previous_cost = tracking_infos[(tracking,)][1] if (tracking,) in tracking_infos else 0.0
            tracking_infos[(tracking,)] = ('oaks', previous_cost + cost_value, '')
          next_page_button = driver.find_element_by_css_selector('input[title="Next Page"]')
          if not next_page_button.is_displayed():
            return tracking_infos, {}
          next_page_button.click()
          time.sleep(2)
          pbar.update()
    finally:
      driver.quit()

  def _get_yrcw_tracking_pos_prices(self) -> ReconResult:
    tracking_info_map: TrackingInfoDict = {}
    po_cost_map: PoCostDict = collections.defaultdict(float)
    driver = self._login_yrcw()
    try:
      time.sleep(5)  # it can take a bit to load

      # show all trackings, not just non-paid
      driver.find_element_by_css_selector('button[title="Filters"]').click()
      time.sleep(2)

      # Clear the date filter (nb: this resets all filters so do it first)
      driver.find_element_by_css_selector('div.modal-body button.ButtonLink').click()
      # 'Any' item status
      select = Select(driver.find_element_by_tag_name('select'))
      select.select_by_visible_text('Any')
      # 'Any' PO status and approval status
      show_any_filter_buttons = driver.find_elements_by_css_selector('input[value="Any"]')
      for any_button in show_any_filter_buttons:
        # we have to click the parent
        any_button.find_element_by_xpath('..').click()
      # Submit it
      driver.find_element_by_css_selector('div.modal-footer .btn-primary').click()

      # hack for yrcw's shitty site with lots of data loading all at once
      yrcw_config = self.config['groups']['yrcw']
      if yrcw_config.get('waitForPageLoad', False):
        input('Wait for all rows on the page to finish loading, then hit enter:')

      # Give it time to load
      time.sleep(10)

      # next load the actual data
      nav_home = driver.find_element_by_id('nav-home')
      table = nav_home.find_element_by_tag_name('table')
      body = table.find_element_by_tag_name('tbody')
      rows = body.find_elements_by_tag_name('tr')
      for row in rows:
        tds = row.find_elements_by_tag_name('td')
        if len(tds) > 1:  # there's a ghost <tr> at the end
          tracking = str(tds[1].text.upper()).strip()
          # Something screwy is going on here with USPS labels.
          # Strip the first 8 chars
          if len(tracking) == 30:
            tracking = tracking[8:]
          value = float(tds[4].text.replace('$', '').replace(',', ''))
          old_value = tracking_info_map[(tracking,)][1] if (tracking,) in tracking_info_map else 0.0
          tracking_info_map[(tracking,)] = ('yrcw', old_value + value, '')
          po_cost_map[tracking] += value
    finally:
      driver.quit()
    return tracking_info_map, po_cost_map

  def _get_usa_login_headers(self):
    group_config = self.config['groups']['usa']
    creds = {"credentials": group_config['username'], "password": group_config['password']}
    response = requests.post(url=USA_API_LOGIN_URL, data=creds)
    token = response.json()['data']['token']
    return {"Authorization": f"Bearer {token}"}

  def _get_usa_tracking_entries(self, headers):
    result = []
    start = 0
    params = {
        "date_from": "",
        "date_until": "",
        "tracking_number": "",
        "receiving_status_id": "1",
        "limit": "100",
        "start": start
    }
    while True:
      params['start'] = start
      json_result = requests.get(url=USA_API_TRACKINGS_URL, headers=headers, params=params).json()
      total_items = json_result['totals']['items']
      result.extend(json_result['data'])
      start += 100
      if start >= total_items:
        break
    return result

  async def _retrieve_usa_tracking_price(self, tracking_number, session,
                                         tracking_tuples_to_prices: TrackingInfoDict):
    try:
      response = await session.request(
          method="GET", url=f"{USA_API_TRACKINGS_URL}/{tracking_number}")
      response.raise_for_status()
      json = await response.json()
      cost = float(json['data']['box']['total_price'])
      tracking_tuples_to_prices[(tracking_number,)] = ('usa', cost, '')
    except Exception as e:
      print(f"Error finding USA tracking cost for {tracking_number}")
      print(e)

  async def _get_usa_tracking_pos_prices(self) -> ReconResult:
    headers = self._get_usa_login_headers()
    pos_to_prices: PoCostDict = {}
    all_entries = self._get_usa_tracking_entries(headers)
    for entry in all_entries:
      pos_to_prices[entry['purchase_id']] = float(entry['purchase']['amount'])
    tracking_numbers = [entry['tracking_number'] for entry in all_entries]
    async with aiohttp.ClientSession(headers=headers) as session:
      tracking_tuples_to_prices: TrackingInfoDict = {}
      tasks = []
      for tracking_number in tracking_numbers:
        tasks.append(
            self._retrieve_usa_tracking_price(tracking_number, session, tracking_tuples_to_prices))
      await asyncio.gather(*tasks)
      return tracking_tuples_to_prices, pos_to_prices

  def _upload_usa(self, numbers) -> None:
    headers = self._get_usa_login_headers()
    data = {"trackings": ",".join(numbers)}
    requests.post(url=USA_API_TRACKINGS_URL, headers=headers, data=data)

  # Downloads the CSV export for the group in question and returns it as a list of rows as dicts
  def _get_melul_csv(self, group: str, username: str, password: str) -> List[Dict[str, str]]:
    _delete_existing_exports()
    print(f"Loading group {group} via CSV export")
    driver = self._login_melul(group, username, password)
    try:
      self._load_page(driver, RECEIPTS_URL_FORMAT % group)
      # Clear out any filters that might have stuck around
      search_button = driver.find_element_by_class_name('pf-search-button')
      search_button.click()
      time.sleep(1)
      driver.find_element_by_xpath('//button[@title="Clear filters only"]').click()
      time.sleep(1)

      # Now download the CSV
      three_dots_button_elems = driver.find_elements_by_css_selector(
          'button.pf-menu-tool-item.launch')
      if not three_dots_button_elems:
        print(f"Could not find CSV export functionality for group {group}.")
        return []
      three_dots_button = three_dots_button_elems[0]
      if three_dots_button.get_attribute('disabled'):
        print(f"No data for group {group}.")
        return []
      three_dots_button.click()
      time.sleep(0.5)
      driver.find_element_by_css_selector(
          'button[ng-click=\'tables["it@receipts"].execTable({cmd:"csv"})\']').click()

      # Wait for the file to be downloaded
      wait_time = 0
      with tqdm(desc=f"Waiting for {group} export file...", unit='second') as pbar:
        while True:
          if os.listdir(MELUL_EXPORTS_FOLDER):
            break
          if wait_time > EXPORT_WAIT_TIMEOUT_SECONDS:
            print(
                f"Waited longer than {EXPORT_WAIT_TIMEOUT_SECONDS} seconds for group {group}. Skipping..."
            )
            return []
          time.sleep(1)
          pbar.update()
          wait_time += 1
      # now the file exists, we assume
      export_csv_file = f"{MELUL_EXPORTS_FOLDER}/{os.listdir(MELUL_EXPORTS_FOLDER)[0]}"
      with open(export_csv_file, 'r') as f:
        reader = csv.DictReader(f)
        return [r for r in reader]
    finally:
      driver.quit()

  def _melul_get_tracking_pos_costs_maps(self, group: str, username: str,
                                         password: str) -> ReconResult:
    csv_rows = self._get_melul_csv(group, username, password)
    po_to_cost_map: PoCostDict = {}
    tracking_infos: TrackingInfoDict = {}
    for row in csv_rows:
      void = row['VOID'] == '1'
      verified = row['VERIFIED'] == '1'
      po = row['ID']
      cost = float(row['TOTAL'])
      date_str = row['CREATED DATE']
      date = datetime.datetime.strptime(date_str, '%a %b %d %Y %H:%M:%S %z').strftime('%Y-%m-%d')
      trackings = clean_csv_tracking(row['TRACKING NUMBERS']).split(',')
      if trackings:
        tracking_tuple = tuple(
            [tracking.strip() for tracking in trackings if tracking and tracking.strip()])
        if cost:
          previous_cost = tracking_infos[tracking_tuple][
              1] if tracking_tuple in tracking_infos else 0.0
          new_cost = float(cost) if (verified and not void) else 0.0
          tracking_infos[tracking_tuple] = (group, previous_cost + new_cost, date)
      if cost and po:
        po_to_cost_map[po] = po_to_cost_map.get(po, 0.0) + float(cost)
    return tracking_infos, po_to_cost_map

  def _upload_to_group(self, numbers: List[str], group: str) -> None:
    last_ex = None
    for attempt in range(MAX_UPLOAD_ATTEMPTS):
      try:
        print("Uploading to %s." % group)
        if group in self.melul_portal_groups:
          username = self.config['groups'][group]['username']
          password = self.config['groups'][group]['password']
          self._upload_melul(numbers, group, username, password)
        elif group == "usa":
          self._upload_usa(numbers)
        elif group == "yrcw":
          self._upload_yrcw(numbers)
        elif group == "bfmr":
          self._upload_bfmr(numbers)
        elif group == 'oaks':
          self._upload_oaks(numbers)
        elif group == 'dtmd':
          self._upload_dtmd(numbers)
        elif group == 'embdeals':
          self._upload_emb(numbers)
        else:
          raise Exception("Unknown group: " + group)

        print("Upload complete for %s." % group)
        return
      except Exception as e:
        last_ex = e
        print("Received exception when uploading: " + str(e))
        traceback.print_exc(file=sys.stdout)
    raise Exception("Exceeded retry limit") from last_ex

  def _load_page(self, driver, url) -> None:
    driver.get(url)
    time.sleep(3)

  def _login_dtmd(self):
    group_config = self.config['groups']['dtmd']
    username = group_config['username']
    password = group_config['password']
    driver = self.driver_creator.new()
    self._load_page(driver, DTMD_URL)
    # There are no ids, names, or class names that are useful at all so we have to use xpath / text
    driver.find_element_by_xpath('//button[text() = "SIGN UP OR LOGIN"]').click()
    # takes a sec to bring up the modal
    time.sleep(1)
    driver.find_element_by_xpath('//button[text() = "OR LOGIN"]').click()
    # takes a sec to bring up the true login page
    time.sleep(1)
    driver.find_element_by_css_selector('input[type="email"]').send_keys(username)
    driver.find_element_by_css_selector('input[type="password"]').send_keys(password)
    driver.find_element_by_xpath('//button[text() = "LOG IN"]').click()
    time.sleep(3)
    return driver

  def _upload_dtmd(self, numbers: List[str]):
    driver = self._login_dtmd()
    try:
      # There are no ids, names, or class names that are useful at all so we have to use xpath / text
      driver.find_element_by_xpath('//button[text() = "Submit Tracking"]').click()
      time.sleep(0.5)
      textarea = driver.find_element_by_tag_name('textarea')
      textarea.send_keys("\n".join(numbers))
      group_selector = Select(driver.find_element_by_tag_name('select'))
      group_selector.select_by_visible_text('DTMD')
      # Same text in the modal's submit field, so select the last one with this text
      driver.find_elements_by_xpath('//button[text() = "Submit Tracking"]')[-1].click()
      # If we close out too soon it aborts the PUT request (which seems to be unrelated to the button click) so sleep
      time.sleep(5)
    finally:
      driver.quit()

  def _login_emb(self) -> WebDriver:
    group_config = self.config['groups']['embdeals']
    username = group_config['username']
    password = group_config['password']
    driver = self.driver_creator.new()

    # the website is terrible, give it leeway
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)
    driver.implicitly_wait(30)
    self._load_page(driver, EMB_URL)
    
    driver.find_element_by_name('email').send_keys(username)
    driver.find_element_by_name('password').send_keys(password)
    driver.find_element_by_css_selector('app-login .mat-button-wrapper').click()
    time.sleep(3)
    return driver

  def _upload_emb(self, numbers) -> None:
    driver = self._login_emb()
    try:
      time.sleep(1)
      #Open menu and navigate to Tracking page
      driver.find_element_by_xpath("//mat-icon[text() = 'menu']").click()
      #EMB site is slow
      time.sleep(1)
      driver.find_element_by_xpath("//span[text() = 'Tracking']").click()
      time.sleep(1)

      #add trackings
      driver.find_element_by_xpath("//span[text() = ' Bulk Tracking']").click()
      driver.find_element_by_name('numbers').send_keys('\n'.join(numbers))

      #submit - EMB site is slow
      driver.implicitly_wait(120)
      driver.find_element_by_xpath("//span[text() = 'Add']").click()

      #wait for trackings to be saved
      driver.find_element_by_xpath("//span[text() = 'saved']")
    finally:
      driver.quit()

  def _login_oaks(self) -> WebDriver:
    group_config = self.config['groups']['oaks']
    username = group_config['username']
    password = group_config['password']
    driver = self.driver_creator.new()
    # the website is terrible, give it leeway
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)
    driver.implicitly_wait(30)
    self._load_page(driver, OAKS_URL)
    # spanglish
    driver.find_element_by_id('txtUsuario').send_keys(username)
    driver.find_element_by_id('txtContrasenia').send_keys(password)
    driver.find_element_by_id('btnIngresar').click()
    time.sleep(3)
    return driver

  def _upload_oaks(self, numbers) -> None:
    driver = self._login_oaks()
    try:
      driver.find_element_by_id('ContentPlaceHolder1_btnUpload').click()
      time.sleep(1)
      # driver.send_keys() is way too slow; this is instant.
      js_input = '\\n'.join(numbers)
      driver.execute_script(f"document.getElementsByTagName('textarea')[0].value = '{js_input}';")
      driver.find_element_by_id('ContentPlaceHolder1_btnGrabar').click()
      time.sleep(2)
    finally:
      driver.quit()

  def _upload_bfmr(self, numbers) -> None:
    for batch in util.chunks(numbers, 100):
      self._upload_bfmr_batch(batch)

  def _upload_bfmr_batch(self, numbers) -> None:
    group_config = self.config['groups']['bfmr']
    former_headless = self.driver_creator.args.headless
    self.driver_creator.args.headless = False
    driver = self.driver_creator.new()
    self.driver_creator.args.headless = former_headless
    try:
      # load the login page first
      self._load_page(driver, "https://buyformeretail.com/login")
      driver.find_element_by_id("email").send_keys(group_config['username'])
      driver.find_element_by_id("password").send_keys(group_config['password'])
      driver.find_element_by_css_selector('div.bfmr-auth-form-next button').click()

      time.sleep(2)

      # hope there's a button to submit tracking numbers -- it doesn't matter which one
      try:
        driver.find_element_by_css_selector('div.view-deal-section button').click()
      except NoSuchElementException:
        raise Exception(
            "Could not find submit-trackings button. Make sure that you've subscribed to a deal and that the login credentials are correct"
        )

      time.sleep(2)

      textarea = driver.find_element_by_css_selector('div.modal-content textarea')
      textarea.send_keys("\n".join(numbers))
      driver.find_element_by_css_selector('div.modal-content button.btn-green').click()
      # TODO: This needs to wait for the success dialog to be displayed.
      time.sleep(5)

      # If there are some dupes, we need to remove the dupes and submit again
      modal = driver.find_element_by_class_name("modal-body")
      if "Tracking number was already entered" in modal.text:
        dupes_list = driver.find_element_by_css_selector('ul.error-message > li.ng-star-inserted')
        dupe_numbers = dupes_list.text.strip().split(", ")
        new_numbers = [n for n in numbers if not n in dupe_numbers]
        driver.find_element_by_class_name("modal-close").click()
        if len(new_numbers) > 0:
          # Re-run this batch with only new numbers, if there are any
          self._upload_bfmr_batch(new_numbers)
    finally:
      driver.quit()

  def _upload_yrcw(self, numbers) -> None:
    driver = self._login_yrcw()
    try:
      self._load_page(driver, YRCW_URL + "dashboard")
      driver.find_element_by_xpath("//button[@data-target='#modalAddTrackingNumbers']").click()
      time.sleep(0.5)
      driver.find_element_by_tag_name("textarea").send_keys(",".join(numbers))
      driver.find_element_by_xpath("//button[text() = 'Add']").click()
      time.sleep(0.5)
      driver.find_element_by_xpath("//button[text() = 'Submit All']").click()
      time.sleep(5)
    finally:
      driver.quit()

  def _upload_melul(self, numbers, group, username, password) -> None:
    driver = self._login_melul(group, username, password)
    try:
      self._load_page(driver, MANAGEMENT_URL_FORMAT % group)

      textareas = driver.find_elements_by_tag_name("textarea")
      if not textareas:
        # omg sellerspeed wyd (show import wizard)
        driver.find_element_by_css_selector('button.pf-menu-tool-item.ng-scope').click()
        time.sleep(1)
        textareas = driver.find_elements_by_tag_name("textarea")
        if not textareas:
          raise Exception("Could not find order management for group %s" % group)

      # driver.send_keys() is way too slow; this is instant.
      js_input = '\\n'.join(numbers)
      driver.execute_script(f"document.getElementsByTagName('textarea')[0].value = '{js_input}';")
      textareas[0].send_keys("\n")  # Trigger blur to enable Submit button.
      driver.find_element_by_xpath(SUBMIT_BUTTON_SELECTOR).click()
      # TODO: This needs to wait for the success dialog to be displayed and then print the number
      #       of new trackings from that to the command line.
      time.sleep(5)
    finally:
      driver.quit()

  def _login_melul(self, group, username, password) -> WebDriver:
    # Always use no-headless for Melul portals for CAPTCHA solving,
    # and save previous headless state and restore it aftewards.
    former_headless = self.driver_creator.args.headless
    self.driver_creator.args.headless = False
    driver = self.driver_creator.new()
    self.driver_creator.args.headless = former_headless
    self._load_page(driver, BASE_URL_FORMAT % group)
    driver.find_element_by_name(LOGIN_EMAIL_FIELD).send_keys(username)
    driver.find_element_by_name(LOGIN_PASSWORD_FIELD).send_keys(password)
    driver.find_element_by_xpath(LOGIN_BUTTON_SELECTOR).click()
    time.sleep(1)

    # Sometimes, they use two-factor auth
    if "Authentication required" in driver.page_source:
      # ask for the email code
      driver.find_element_by_css_selector("md-radio-button[value='email']").click()
      driver.find_element_by_css_selector("button[type='submit']").click()
      print(f"Solve the CAPTCHA for group {group}, then WAIT FOR THE 2FA EMAIL.")
      input("Press Return once the email has arrived (don't open it): ")
      print("Fetching 2FA code from email ...")

      # get the email client and search for the code
      mail = self._get_all_mail_folder()
      _, email_ids = mail.uid('SEARCH', None, '(SUBJECT "Passcode for")')
      last_id = email_ids[0].split()[-1]
      _, data = mail.uid("FETCH", last_id, "(RFC822)")
      msg = email.message_from_string(str(data[0][1], 'utf-8'))
      subject = msg['Subject']
      pattern = r'Passcode for .*(\d{3}-\d{3})'
      code = re.match(pattern, subject).group(1).replace('-', '')
      print(f"Found passcode {code}, submitting ...")

      driver.find_element_by_css_selector('input[ui-mask="999-999"]').send_keys(code)
      time.sleep(1)
      # The "Authenticate" button is the last button on the page.
      driver.find_elements_by_css_selector("button[type='submit']")[-1].click()
      time.sleep(1)

    return driver

  def _login_yrcw(self) -> WebDriver:
    driver = self.driver_creator.new()
    self._load_page(driver, YRCW_URL)
    group_config = self.config['groups']['yrcw']
    driver.find_element_by_xpath("//input[@type='email']").send_keys(group_config['username'])
    driver.find_element_by_xpath("//input[@type='password']").send_keys(group_config['password'])
    driver.find_element_by_xpath("//button[@type='submit']").click()
    time.sleep(2)
    return driver

  def _get_all_mail_folder(self) -> IMAP4_SSL:
    mail = email_auth.email_authentication()
    mail.select('"[Gmail]/All Mail"')
    return mail

  def _get_bfmr_costs(self) -> TrackingInfoDict:
    mail = self._get_all_mail_folder()
    status, response = mail.uid('SEARCH', None, 'SUBJECT "Payment Sent"', 'SINCE "01-Aug-2019"',
                                'FROM "deals@buyformeretail.com"')
    email_ids = response[0].decode('utf-8').split()
    result: TrackingInfoDict = {}

    for email_id in tqdm(email_ids, desc='Fetching BFMR check-ins', unit='email'):
      email_str = email_tracking_retriever.get_email_content(email_id, mail)
      msg = email.message_from_string(email_str)
      date = datetime.datetime.strptime(
          msg['Date'], '%a, %d %b %Y %H:%M:%S %z').strftime('%Y-%m-%d') if msg['Date'] else ''
      email_str = email_tracking_retriever.clean_email_content(email_str)
      soup = BeautifulSoup(email_str, features="html.parser")

      body = soup.find('td', id='email_body')
      if not body:
        continue
      tables = body.find_all('table')
      if not tables or len(tables) < 2:
        continue
      table = tables[1]
      fill_busted_bfmr_costs(result, table, date)
      fill_standard_bfmr_costs(result, table, date)
      fill_2020_12_22_bfmr_costs(result, table, date)

    return result
