import asyncio
import collections
import email
import quopri
import re
import sys
import time
import traceback
from typing import Any

import aiohttp
import requests
from bs4 import BeautifulSoup
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import Select
from tqdm import tqdm

import lib.email_auth as email_auth
from lib import util
from lib.archive_manager import ArchiveManager

LOGIN_EMAIL_FIELD = "fldEmail"
LOGIN_PASSWORD_FIELD = "fldPassword"
LOGIN_BUTTON_SELECTOR = "//button[contains(text(), 'Login')]"

SUBMIT_BUTTON_SELECTOR = "//*[contains(text(), 'SUBMIT')]"

RESULT_SELECTOR = "//*[contains(text(), 'record(s) effected')]"
RESULT_REGEX = r"(\d+) record\(s\) effected"

BASE_URL_FORMAT = "https://%s.com"
MANAGEMENT_URL_FORMAT = "https://www.%s.com/p/it@orders-all/"

RECEIPTS_URL_FORMAT = "https://%s.com/p/it@receipts"

USA_LOGIN_URL = "https://usabuying.group/login"
USA_TRACKING_URL = "https://usabuying.group/trackings"
USA_PO_URL = "https://usabuying.group/purchase-orders"

USA_API_LOGIN_URL = "https://api.usabuying.group/index.php/buyers/login"
USA_API_TRACKINGS_URL = "https://api.usabuying.group/index.php/buyers/trackings"

YRCW_URL = "https://app.yrcwtech.com/"

MAX_UPLOAD_ATTEMPTS = 10


class GroupSiteManager:

  def __init__(self, config, driver_creator) -> None:
    self.config = config
    self.driver_creator = driver_creator
    self.melul_portal_groups = config['melulPortals']
    self.archive_manager = ArchiveManager(config)

  def get_tracked_groups(self):
    result = set(self.melul_portal_groups)
    result.add('bfmr')
    result.add('usa')
    result.add('yrcw')
    return result

  def upload(self, trackings) -> None:
    groups_dict = collections.defaultdict(list)
    for tracking in trackings:
      groups_dict[tracking.group].append(tracking)

    for group, trackings in groups_dict.items():
      numbers = [tracking.tracking_number for tracking in trackings]
      group_config = self.config['groups'][group]
      if group_config.get('password') and group_config.get('username'):
        self._upload_to_group(numbers, group)

  def get_new_tracking_pos_costs_maps_with_retry(self, group):
    last_exc = None
    for i in range(5):
      try:
        return self.get_new_tracking_pos_costs_maps(group)
      except Exception as e:
        print(f"Received exception when getting costs: {str(e)}\n{util.get_traceback_lines()}\n"
              "Retrying up to five times.")
        last_exc = e
    raise Exception("Exceeded retry limit", last_exc)

  # returns ((trackings) -> cost, po -> cost) maps
  def get_new_tracking_pos_costs_maps(self, group):
    if group == 'bfmr':
      print("Loading BFMR emails")
      _, costs_map = self._get_bfmr_costs()
      trackings_map = {}
      for tracking, cost in costs_map.items():
        trackings_map[(tracking,)] = cost
      return (trackings_map, costs_map)
    elif group in self.melul_portal_groups:
      group_config = self.config['groups'][group]
      username = group_config['username']
      password = group_config['password']
      _, po_cost, trackings_cost = self._melul_get_tracking_pos_costs_maps(
          group, username, password)

      if 'archives' in group_config:
        for archive_group in group_config['archives']:
          print(f"Loading archive {archive_group}")
          if not self.archive_manager.has_archive(archive_group):
            _, archive_po_cost, archive_trackings_cost = self._melul_get_tracking_pos_costs_maps(
                archive_group, username, password)
            self.archive_manager.put_archive(archive_group, archive_po_cost, archive_trackings_cost)

          archive_po_cost, archive_trackings_cost = self.archive_manager.get_archive(archive_group)
          po_cost.update(archive_po_cost)
          trackings_cost.update(archive_trackings_cost)

      return trackings_cost, po_cost
    elif group == "usa":
      print("Loading group usa")
      return asyncio.run(self._get_usa_tracking_pos_prices())
    elif group == "yrcw":
      print("Loading yrcw")
      return self._get_yrcw_tracking_pos_prices()
    return (dict(), dict())

  # returns ((trackings) -> cost, po -> cost) maps
  def _get_yrcw_tracking_pos_prices(self):
    tracking_cost_map = collections.defaultdict(float)
    po_cost_map = collections.defaultdict(float)
    driver = self._login_yrcw()
    try:
      time.sleep(5)  # it can take a bit to load

      # show all trackings, not just non-paid
      driver.find_element_by_css_selector('button[title="Filters"]').click()
      time.sleep(2)
      select = Select(driver.find_element_by_tag_name('select'))
      select.select_by_visible_text('Any')

      driver.find_element_by_css_selector('div.modal-footer .btn-primary').click()
      time.sleep(2)

      # next load the actual data
      nav_home = driver.find_element_by_id('nav-home')
      table = nav_home.find_element_by_tag_name('table')
      body = table.find_element_by_tag_name('tbody')
      rows = body.find_elements_by_tag_name('tr')
      for row in rows:
        tds = row.find_elements_by_tag_name('td')
        if len(tds) > 1:  # there's a ghost <tr> at the end
          tracking = tds[1].text.upper().strip()
          # Something screwy is going on here with USPS labels.
          # Strip the first 8 chars
          if len(tracking) == 30:
            tracking = tracking[8:]
          value = float(tds[4].text.replace('$', '').replace(',', ''))
          tracking_cost_map[(tracking,)] += value
          po_cost_map[tracking] += value
    finally:
      driver.close()
    return tracking_cost_map, po_cost_map

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

  async def _retrieve_usa_tracking_price(self, tracking_number, session, tracking_tuples_to_prices):
    try:
      response = await session.request(
          method="GET", url=f"{USA_API_TRACKINGS_URL}/{tracking_number}")
      response.raise_for_status()
      json = await response.json()
      cost = float(json['data']['box']['total_price'])
      tracking_tuples_to_prices[(tracking_number,)] = cost
    except Exception as e:
      print(f"Error finding USA tracking cost for {tracking_number}")
      print(e)

  async def _get_usa_tracking_pos_prices(self):
    headers = self._get_usa_login_headers()
    pos_to_prices = {}
    all_entries = self._get_usa_tracking_entries(headers)
    for entry in all_entries:
      po_id = entry['purchase_id']
      pos_to_prices[po_id] = float(entry['purchase']['amount'])
    tracking_numbers = [entry['tracking_number'] for entry in all_entries]
    async with aiohttp.ClientSession(headers=headers) as session:
      tracking_tuples_to_prices = {}
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

  # hacks, return tracking->po, po->cost, (trackings)->cost
  def _melul_get_tracking_pos_costs_maps(self, group, username, password):
    driver = self._login_melul(group, username, password)
    try:
      self._load_page(driver, RECEIPTS_URL_FORMAT % group)
      tracking_to_po_map = {}
      po_to_cost_map = {}
      trackings_to_cost_map = {}

      # Clear the search field since it can cache results
      search_button = driver.find_element_by_class_name('pf-search-button')
      search_button.click()
      time.sleep(1)
      driver.find_element_by_xpath('//button[@title="Clear filters"]').click()
      time.sleep(1)
      driver.find_element_by_xpath('//md-icon[text()="last_page"]').click()
      time.sleep(4)

      # go to the first page (page selection can get a bit messed up with the multiple sites)
      # use a list to avoid throwing an exception (don't fail if there's only one page)
      first_page_buttons = driver.find_elements_by_xpath(
          "//button[@ng-click='$pagination.first()']")
      if first_page_buttons:
        first_page_buttons[0].click()
        time.sleep(4)

      with tqdm(desc=f"Fetching {group} check-ins", unit='page') as pbar:
        while True:
          table = driver.find_element_by_xpath("//tbody[@class='md-body']")
          rows = table.find_elements_by_tag_name('tr')
          for row in rows:
            tds = row.find_elements_by_tag_name('td')
            verified_checkbox = tds[4].find_element_by_tag_name('md-checkbox')
            verified = 'md-checked' in verified_checkbox.get_attribute('class')
            po = str(tds[5].text)
            cost = tds[13].text.replace('$', '').replace(',', '')
            trackings = tds[14].text.replace('-', '').split(",")

            if trackings:
              trackings = [tracking.strip() for tracking in trackings if tracking]
              if cost:
                trackings_to_cost_map[tuple(trackings)] = float(cost) if verified else 0.0
              for tracking in trackings:
                tracking_to_po_map[tracking] = po
            if cost and po:
              po_to_cost_map[po] = float(cost)

          next_page_buttons = driver.find_elements_by_xpath(
              "//button[@ng-click='$pagination.next()']")
          if next_page_buttons and next_page_buttons[0].get_property("disabled") == False:
            next_page_buttons[0].click()
            time.sleep(3)
            pbar.update()
          else:
            break

        return (tracking_to_po_map, po_to_cost_map, trackings_to_cost_map)
    finally:
      driver.close()

  def _upload_to_group(self, numbers, group) -> None:
    last_ex = None
    for attempt in range(MAX_UPLOAD_ATTEMPTS):
      try:
        if group in self.melul_portal_groups:
          username = self.config['groups'][group]['username']
          password = self.config['groups'][group]['password']
          return self._upload_melul(numbers, group, username, password)
        elif group == "usa":
          return self._upload_usa(numbers)
        elif group == "yrcw":
          return self._upload_yrcw(numbers)
        elif group == "bfmr":
          return self._upload_bfmr(numbers)
        else:
          raise Exception("Unknown group: " + group)
      except Exception as e:
        last_ex = e
        print("Received exception when uploading: " + str(e))
        traceback.print_exc(file=sys.stdout)
    raise Exception("Exceeded retry limit") from last_ex

  def _load_page(self, driver, url) -> None:
    driver.get(url)
    time.sleep(3)

  def _upload_bfmr(self, numbers) -> None:
    for batch in util.chunks(numbers, 30):
      self._upload_bfmr_batch(batch)

  def _upload_bfmr_batch(self, numbers) -> None:
    group_config = self.config['groups']['bfmr']
    driver = self.driver_creator.new()
    try:
      # load the login page first
      self._load_page(driver, "https://buyformeretail.com/login")
      driver.find_element_by_id("loginEmail").send_keys(group_config['username'])
      driver.find_element_by_id("loginPassword").send_keys(group_config['password'])
      driver.find_element_by_xpath("//button[@type='submit']").click()

      time.sleep(2)

      # hope there's a button to submit tracking numbers -- it doesn't matter which one
      try:
        submit_button = driver.find_element_by_xpath("//button[text() = \"Submit tracking #'s\"]")
        submit_button.click()
      except NoSuchElementException:
        raise Exception(
            "Could not find submit-trackings button. Make sure that you've subscribed to a deal and that the login credentials are correct"
        )

      time.sleep(2)

      modal = driver.find_element_by_class_name("modal-body")
      form = modal.find_element_by_tag_name("form")

      textarea = form.find_element_by_class_name("textarea-control")
      textarea.send_keys("\n".join(numbers))
      form.find_element_by_xpath("//button[text() = 'Submit']").click()
      time.sleep(1)

      # If there are some dupes, we need to remove the dupes and submit again
      modal = driver.find_element_by_class_name("modal-body")
      if "Tracking number was already entered" in modal.text:
        dupes_list = form.find_element_by_css_selector('ul.error-message > li.ng-star-inserted')
        dupe_numbers = dupes_list.text.strip().split(", ")
        new_numbers = [n for n in numbers if not n in dupe_numbers]
        driver.find_element_by_class_name("modal-close").click()
        if len(new_numbers) > 0:
          # Re-run this batch with only new numbers, if there are any
          self._upload_bfmr_batch(driver, new_numbers)
    finally:
      driver.close()

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
      time.sleep(2)
    finally:
      driver.close()

  def _upload_melul(self, numbers, group, username, password) -> None:
    driver = self._login_melul(group, username, password)
    try:
      self._load_page(driver, MANAGEMENT_URL_FORMAT % group)

      textareas = driver.find_elements_by_tag_name("textarea")
      if not textareas:
        # omg sellerspeed wyd
        driver.find_element_by_xpath("//span[text() = ' Show Import wizard']").click()
        time.sleep(1)
        textareas = driver.find_elements_by_tag_name("textarea")
        if not textareas:
          raise Exception("Could not find order management for group %s" % group)

      textarea = textareas[0]
      textarea.send_keys('\n'.join(numbers))
      driver.find_element_by_xpath(SUBMIT_BUTTON_SELECTOR).click()
      time.sleep(1)
    finally:
      driver.close()

  def _login_melul(self, group, username, password) -> Any:
    # Always use no-headless for Melul portals for CAPTCHA solving,
    # and save previous no-headless state and restore it aftewards.
    former_headless = self.driver_creator.args.no_headless
    self.driver_creator.args.no_headless = True
    driver = self.driver_creator.new()
    self.driver_creator.args.no_headless = former_headless
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

  def _login_yrcw(self) -> Any:
    driver = self.driver_creator.new()
    self._load_page(driver, YRCW_URL)
    group_config = self.config['groups']['yrcw']
    driver.find_element_by_xpath("//input[@type='email']").send_keys(group_config['username'])
    driver.find_element_by_xpath("//input[@type='password']").send_keys(group_config['password'])
    driver.find_element_by_xpath("//button[@type='submit']").click()
    time.sleep(2)
    return driver

  def _get_all_mail_folder(self):
    mail = email_auth.email_authentication()
    mail.select('"[Gmail]/All Mail"')
    return mail

  def _get_bfmr_costs(self):
    mail = self._get_all_mail_folder()
    status, response = mail.uid('SEARCH', None, 'SUBJECT "BuyForMeRetail - Payment Sent"',
                                'SINCE "01-Aug-2019"')
    email_ids = response[0].decode('utf-8').split()
    # some hacks, "po" will just also be the tracking
    tracking_map = dict()
    result = collections.defaultdict(float)

    for email_id in tqdm(email_ids, desc='Fetching BFMR check-ins', unit='email'):
      fetch_result, data = mail.uid("FETCH", email_id, "(RFC822)")
      soup = BeautifulSoup(
          quopri.decodestring(data[0][1]), features="html.parser", from_encoding="iso-8859-1")

      body = soup.find('td', id='email_body')
      if not body:
        continue
      tables = body.find_all('table')
      if not tables or len(tables) < 2:
        continue
      table = tables[1]
      trs = table.find_all('tr')
      # busted-ass html doesn't close the <tr> tags until the end
      tds = trs[1].find_all('td')
      # shave out the "total amount" tds
      tds = tds[:-2]

      for i in range(len(tds) // 5):
        tracking = tds[i * 5].getText().upper()
        total_text = tds[i * 5 + 4].getText()
        total = float(total_text.replace(',', '').replace('$', ''))
        result[tracking] += total
        tracking_map[tracking] = tracking

    return (tracking_map, result)
