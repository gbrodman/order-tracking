import collections
import imaplib
import quopri
import re
import requests
import sys
import time
import traceback

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from tqdm import tqdm
from typing import Any, Dict

LOGIN_EMAIL_FIELD = "fldEmail"
LOGIN_PASSWORD_FIELD = "fldPassword"
LOGIN_BUTTON_SELECTOR = "//button[contains(text(), 'Login')]"

SUBMIT_BUTTON_SELECTOR = "//*[contains(text(), 'SUBMIT')]"

RESULT_SELECTOR = "//*[contains(text(), 'record(s) effected')]"
RESULT_REGEX = r"(\d+) record\(s\) effected"

BASE_URL_FORMAT = "https://www.%s.com"
MANAGEMENT_URL_FORMAT = "https://www.%s.com/p/it@orders-all/"

RECEIPTS_URL_FORMAT = "https://%s.com/p/it@receipts"

USA_LOGIN_URL = "https://usabuying.group/login"
USA_TRACKING_URL = "https://usabuying.group/trackings"
USA_PO_URL = "https://usabuying.group/purchase-orders"

USA_API_LOGIN_URL = "https://api.usabuying.group/index.php/buyers/login"
USA_API_TRACKINGS_URL = "https://api.usabuying.group/index.php/buyers/trackings"

YRCW_URL = "https://app.xchaintechnology.com/"

MAX_UPLOAD_ATTEMPTS = 10


class GroupSiteManager:

  def __init__(self, config, driver_creator) -> None:
    self.config = config
    self.driver_creator = driver_creator
    self.melul_portal_groups = config['melulPortals']

  def upload(self, trackings) -> None:
    groups_dict = collections.defaultdict(list)
    for tracking in trackings:
      groups_dict[tracking.group].append(tracking)

    for group, trackings in groups_dict.items():
      numbers = [tracking.tracking_number for tracking in trackings]
      group_config = self.config['groups'][group]
      if group_config.get('password') and group_config.get('username'):
        self._upload_to_group(numbers, group)

  def get_tracking_pos_costs_maps_with_retry(self, group):
    last_exc = None
    for i in range(5):
      try:
        return self.get_tracking_pos_costs_maps(group)
      except Exception as e:
        print("Received exception when getting costs: " + str(e))
        type, value, trace = sys.exc_info()
        formatted_trace = traceback.format_tb(trace)
        for line in formatted_trace:
          print(line)
        print("Retrying up to five times")
        last_exc = e
    raise Exception("Exceeded retry limit", last_exc)

  # returns (tracking -> po, po -> cost) dicts
  def get_tracking_pos_costs_maps(self, group):
    if group == 'bfmr':
      print("Loading group bfmr")
      return self._get_bfmr_costs()
    elif group in self.melul_portal_groups:
      print("Loading group %s" % group)
      return self._melul_get_tracking_pos_costs_maps(group)
    elif group == "usa":
      print("Loading group usa")
      return self._get_usa_tracking_pos_costs_maps()
    return (dict(), dict())

  def _get_usa_login_headers(self):
    group_config = self.config['groups']['usa']
    creds = {
        "credentials": group_config['username'],
        "password": group_config['password']
    }
    response = requests.post(url=USA_API_LOGIN_URL, data=creds)
    token = response.json()['data']['token']
    return {"Authorization": f"Bearer {token}"}

  def _upload_usa(self, numbers) -> None:
    headers = self._get_usa_login_headers()
    data = {"trackings": ",".join(numbers)}
    requests.post(url=USA_API_TRACKINGS_URL, headers=headers, data=data)

  def _get_usa_tracking_pos_costs_maps(self):
    po_to_cost = self._get_usa_po_to_price()
    tracking_to_po = self._get_usa_tracking_to_purchase_order()
    return (tracking_to_po, po_to_cost)

  def _melul_get_tracking_pos_costs_maps(self, group):
    driver = self._login_melul(group)
    try:
      self._load_page(driver, RECEIPTS_URL_FORMAT % group)
      tracking_to_po_map = {}
      po_to_cost_map = {}

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

      while True:
        table = driver.find_element_by_xpath("//tbody[@class='md-body']")
        rows = table.find_elements_by_tag_name('tr')
        for row in rows:
          po = str(row.find_elements_by_tag_name('td')[5].text)
          cost = row.find_elements_by_tag_name('td')[13].text.replace(
              '$', '').replace(',', '')
          trackings = row.find_elements_by_tag_name('td')[14].text.replace(
              '-', '').split(",")

          print("PO: %s, Tracking(s): %s, Cost: $%.2f" %
                (po, ",".join(trackings), float(cost)))

          if trackings:
            for tracking in trackings:
              if tracking:
                tracking_to_po_map[tracking.strip()] = po
          if cost and po:
            po_to_cost_map[po] = float(cost)

        next_page_buttons = driver.find_elements_by_xpath(
            "//button[@ng-click='$pagination.next()']")
        if next_page_buttons and next_page_buttons[0].get_property(
            "disabled") == False:
          next_page_buttons[0].click()
          time.sleep(3)
        else:
          break

      return (tracking_to_po_map, po_to_cost_map)
    finally:
      driver.close()

  def _upload_to_group(self, numbers, group) -> None:
    for attempt in range(MAX_UPLOAD_ATTEMPTS):
      try:
        if group in self.melul_portal_groups:
          return self._upload_melul(numbers, group)
        elif group == "usa":
          return self._upload_usa(numbers)
        elif group == "yrcw":
          return self._upload_yrcw(numbers)
        elif group == "bfmr":
          return self._upload_bfmr(numbers)
        else:
          raise Exception("Unknown group: " + group)
      except Exception as e:
        print("Received exception when uploading: " + str(e))
    raise Exception("Exceeded retry limit")

  def _load_page(self, driver, url) -> None:
    driver.get(url)
    time.sleep(3)

  def _upload_bfmr(self, numbers) -> None:
    group_config = self.config['groups']['bfmr']
    driver = self.driver_creator.new()
    try:
      # load the login page first
      self._load_page(driver, "https://buyformeretail.com/login")
      driver.find_element_by_id("loginEmail").send_keys(
          group_config['username'])
      driver.find_element_by_id("loginPassword").send_keys(
          group_config['password'])
      driver.find_element_by_xpath("//button[@type='submit']").click()

      time.sleep(2)

      # hope there's a button to submit tracking numbers -- it doesn't matter which one
      try:
        submit_button = driver.find_element_by_xpath(
            "//button[text() = \"Submit tracking #'s\"]")
        submit_button.click()
      except NoSuchElementException:
        raise Exception(
            "Could not find submit-trackings button. Make sure that you've subscribed to a deal and that the login credentials are correct"
        )

      time.sleep(2)

      modal = driver.find_element_by_class_name("modal-body")
      form = modal.find_element_by_tag_name("form")

      # put in the tracking, click the add-new-number button
      for i in range(len(numbers)):
        number = numbers[i]
        input_elem = form.find_elements_by_xpath("//input[@appvalidinput]")[i]
        input_elem.send_keys(number)
        form.find_element_by_xpath(
            "//span[text() = 'Add Tracking number']").click()

      form.find_element_by_xpath("//button[text() = 'Submit']").click()
      time.sleep(1)

      # If there are some dupes, we need to submit twice to confirm that any non-dupes were submitted
      modal = driver.find_element_by_class_name("modal-body")
      if "Some tracking numbers already noted" in modal.text:
        form.find_element_by_xpath("//button[text() = 'Submit']").click()
    finally:
      driver.close()

  def _upload_yrcw(self, numbers) -> None:
    driver = self._login_yrcw()
    try:
      self._load_page(driver, YRCW_URL + "dashboard")
      driver.find_element_by_xpath(
          "//button[@data-target='#modalAddTrackingNumbers']").click()
      time.sleep(0.5)
      driver.find_element_by_tag_name("textarea").send_keys(",".join(numbers))
      driver.find_element_by_xpath("//button[text() = 'Add']").click()
      time.sleep(0.5)
      driver.find_element_by_xpath("//button[text() = 'Submit All']").click()
      time.sleep(2)
    finally:
      driver.close()

  def _upload_melul(self, numbers, group) -> None:
    driver = self._login_melul(group)
    try:
      self._load_page(driver, MANAGEMENT_URL_FORMAT % group)
      textareas = driver.find_elements_by_xpath("//textarea")
      if not textareas:
        print("Could not find order management for group %s" % group)
        return

      textarea = textareas[0]
      textarea.send_keys('\n'.join(numbers))
      driver.find_element_by_xpath(SUBMIT_BUTTON_SELECTOR).click()
      time.sleep(1)
    finally:
      driver.close()

  def _login_melul(self, group) -> Any:
    driver = self.driver_creator.new()
    self._load_page(driver, BASE_URL_FORMAT % group)
    group_config = self.config['groups'][group]
    driver.find_element_by_name(LOGIN_EMAIL_FIELD).send_keys(
        group_config['username'])
    driver.find_element_by_name(LOGIN_PASSWORD_FIELD).send_keys(
        group_config['password'])
    driver.find_element_by_xpath(LOGIN_BUTTON_SELECTOR).click()
    time.sleep(1)
    return driver

  def _usa_set_pagination_100(self, driver) -> None:
    driver.find_element_by_class_name(
        'react-bs-table-pagination').find_element_by_tag_name('button').click()
    driver.find_element_by_css_selector("a[data-page='100']").click()

  def _get_usa_po_to_price(self) -> Dict[Any, float]:
    result = {}
    driver = self._login_usa()
    try:
      with tqdm(desc='Fetching POs', unit='page') as pbar:
        self._load_page(driver, USA_PO_URL)
        time.sleep(1)
        self._usa_set_pagination_100(driver)
        while True:
          time.sleep(2)
          table = driver.find_element_by_class_name("react-bs-container-body")
          rows = table.find_elements_by_tag_name('tr')
          for row in rows:
            entries = row.find_elements_by_tag_name('td')
            po = entries[1].text
            cost = float(entries[5].text.replace('$', '').replace(',', ''))
            result[po] = cost
          pbar.update()
          next_page_button = driver.find_elements_by_xpath(
              "//li[contains(@title, 'next page')]")
          if next_page_button:
            next_page_button[0].find_element_by_tag_name('a').click()
          else:
            break

      return result
    finally:
      driver.close()

  def _get_usa_tracking_to_purchase_order(self) -> dict:
    result = {}
    driver = self._login_usa()
    try:
      with tqdm(desc='Fetching trackings', unit='page') as pbar:
        # Tell the USA tracking search to find received tracking numbers from the beginning of time
        self._load_page(driver, USA_TRACKING_URL)
        date_filter_div = driver.find_element_by_class_name(
            "reports-dates-filter-cnt")
        date_filter_btn = date_filter_div.find_element_by_tag_name("button")
        date_filter_btn.click()
        time.sleep(1)

        date_filter_div.find_element_by_xpath(
            '//a[contains(text(), "None")]').click()
        time.sleep(2)

        status_dropdown = driver.find_element_by_name("filterPurchaseid")
        status_dropdown.click()
        time.sleep(1)

        status_dropdown.find_element_by_xpath("//*[text()='Received']").click()
        time.sleep(1)

        driver.find_element_by_xpath(
            "//i[contains(@class, 'fa-search')]").click()
        time.sleep(1)
        self._usa_set_pagination_100(driver)

        while True:
          time.sleep(4)
          table = driver.find_element_by_class_name("react-bs-container-body")
          rows = table.find_elements_by_tag_name('tr')
          for row in rows:
            entries = row.find_elements_by_tag_name('td')
            tracking = entries[2].text
            purchase_order = entries[3].text.split(' ')[0]
            result[tracking] = purchase_order
          pbar.update()
          next_page_button = driver.find_elements_by_xpath(
              "//li[contains(@title, 'next page')]")
          if next_page_button:
            next_page_button[0].find_element_by_tag_name('a').click()
          else:
            break

      return result
    finally:
      driver.close()

  def _login_usa(self) -> Any:
    driver = self.driver_creator.new()
    self._load_page(driver, USA_LOGIN_URL)
    group_config = self.config['groups']['usa']
    driver.find_element_by_name("credentials").send_keys(
        group_config['username'])
    driver.find_element_by_name("password").send_keys(group_config['password'])
    # for some reason there's an invalid login button in either the first or second array spot (randomly)
    for element in driver.find_elements_by_name("log-me-in"):
      try:
        element.click()
      except:
        pass
    time.sleep(2)
    return driver

  def _login_yrcw(self) -> Any:
    driver = self.driver_creator.new()
    self._load_page(driver, YRCW_URL)
    group_config = self.config['groups']['yrcw']
    driver.find_element_by_xpath("//input[@type='email']").send_keys(
        group_config['username'])
    driver.find_element_by_xpath("//input[@type='password']").send_keys(
        group_config['password'])
    driver.find_element_by_xpath("//button[@type='submit']").click()
    time.sleep(2)
    return driver

  def _get_bfmr_costs(self):
    mail = imaplib.IMAP4_SSL(self.config['email']['imapUrl'])
    mail.login(self.config['email']['username'],
               self.config['email']['password'])
    mail.select('"[Gmail]/All Mail"')
    status, response = mail.uid('SEARCH', None,
                                'SUBJECT "BuyForMeRetail - Payment Sent"',
                                'SINCE "01-Aug-2019"')
    email_ids = response[0].decode('utf-8').split()
    # some hacks, "po" will just also be the tracking
    tracking_map = dict()
    result = collections.defaultdict(float)
    for email_id in email_ids:
      fetch_result, data = mail.uid("FETCH", email_id, "(RFC822)")
      soup = BeautifulSoup(
          quopri.decodestring(data[0][1]), features="html.parser")
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
        print("%s: $%.2f" % (tracking, total))
        result[tracking] += total
        tracking_map[tracking] = tracking

    return (tracking_map, result)
