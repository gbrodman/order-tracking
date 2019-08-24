import time
import re
from selenium import webdriver

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

MAX_UPLOAD_ATTEMPTS = 10


class GroupSiteManager:

  def __init__(self, config, driver_creator):
    self.config = config
    self.driver_creator = driver_creator

  def upload(self, groups_dict):
    for group, trackings in groups_dict.items():
      numbers = [tracking.tracking_number for tracking in trackings]
      group_config = self.config['groups'][group]
      if group_config.get('password') and group_config.get('username'):
        self._upload_to_group(numbers, group, group_config['username'],
                              group_config['password'])

  def get_tracked_costs(self, group):
    if group != "mysbuyinggroup" and group != "pointsmaker":
      raise Exception("Can't find tracked costs for group %s" % group)

    group_config = self.config['groups'][group]
    driver = self._login_mys_pm(group, group_config['username'],
                                group_config['password'])
    try:
      self._load_page(driver, RECEIPTS_URL_FORMAT % group)
      tracking_to_cost_map = {}

      while True:
        table = driver.find_element_by_xpath("//tbody[@class='md-body']")
        rows = table.find_elements_by_tag_name('tr')
        for row in rows:
          cost = row.find_elements_by_tag_name('td')[13].text.replace(
              '$', '').replace(',', '')
          tracking = row.find_elements_by_tag_name('td')[14].text
          tracking_to_cost_map[tracking] = float(cost)

        next_page_button = driver.find_element_by_xpath(
            "//button[@ng-click='$pagination.next()']")
        if next_page_button.get_property("disabled") == False:
          next_page_button.click()
          time.sleep(1)
        else:
          break

      return tracking_to_cost_map
    finally:
      driver.close()

  def _upload_to_group(self, numbers, group, username, password):
    for attempt in range(MAX_UPLOAD_ATTEMPTS):
      try:
        if group == "mysbuyinggroup" or group == "pointsmaker":
          return self._upload_mys_pm(numbers, group, username, password)
        elif group == "usa":
          return self._upload_usa(numbers, username, password)
        else:
          raise Exception("Unknown group: " + group)
      except Exception as e:
        print("Received exception when uploading: " + str(e))
    raise

  def _load_page(self, driver, url):
    driver.get(url)
    time.sleep(2)

  def _upload_mys_pm(self, numbers, group, username, password):
    driver = self._login_mys_pm(group, username, password)
    try:
      self._load_page(driver, MANAGEMENT_URL_FORMAT % group)
      driver.find_element_by_xpath("//textarea").send_keys('\n'.join(numbers))
      driver.find_element_by_xpath(SUBMIT_BUTTON_SELECTOR).click()
      time.sleep(1)
    finally:
      driver.close()

  def _login_mys_pm(self, group, username, password):
    driver = self.driver_creator.new()
    self._load_page(driver, BASE_URL_FORMAT % group)
    driver.find_element_by_name(LOGIN_EMAIL_FIELD).send_keys(username)
    driver.find_element_by_name(LOGIN_PASSWORD_FIELD).send_keys(password)
    driver.find_element_by_xpath(LOGIN_BUTTON_SELECTOR).click()
    time.sleep(1)
    return driver

  def _upload_usa(self, numbers, username, password):
    driver = self.driver_creator.new()
    try:
      self._load_page(driver, USA_LOGIN_URL)
      driver.find_element_by_name("credentials").send_keys(username)
      driver.find_element_by_name("password").send_keys(password)
      # for some reason there's an invalid login button in either the first or second array spot (randomly)
      for element in driver.find_elements_by_name("log-me-in"):
        try:
          element.click()
        except:
          pass

      time.sleep(2)
      self._load_page(driver, USA_TRACKING_URL)
      driver.find_element_by_xpath("//*[contains(text(), ' Add')]").click()
      driver.find_element_by_xpath("//textarea").send_keys("\n".join(numbers))
      time.sleep(1)
      driver.find_element_by_xpath("//*[contains(text(), 'Submit')]").click()
      time.sleep(3)
    finally:
      driver.close()
