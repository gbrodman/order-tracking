import datetime
import os
import re
import time
from typing import Dict, List, Optional, Tuple

from selenium.webdriver.chrome.webdriver import WebDriver
from tqdm import tqdm
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from import_report import do_with_wait
from lib.driver_creator import DriverCreator
from lib.email_tracking_retriever import EmailTrackingRetriever, get_email_content
from lib.tracking import Tracking


def _parse_date(text):
  if not text:
    return ''
  text = text.replace('=20', '')  # extra char can get added
  date_text = text.split(',')[-1].strip()
  date_text = ' '.join(date_text.split(' ')[0:2])
  try:
    date = datetime.datetime.strptime(date_text, "%B %d").replace(year=datetime.datetime.now().year)
    return date.strftime('%Y-%m-%d')
  except:
    return ''


def new_driver(profile_base: str, profile_name: str) -> WebDriver:
  dc = DriverCreator()
  dc.args.no_headless = True
  return dc.new(f"{os.path.expanduser(profile_base)}/{profile_name}")


def find_old_tracking_by_order(order_id: str, existing_trackings: List[Tracking],
                               new_trackings: Dict[str, Tracking]) -> Optional[Tracking]:
  for tracking in existing_trackings:
    if order_id in tracking.order_ids:
      return tracking
  for tracking in new_trackings.values():
    if order_id in tracking.order_ids:
      return tracking
  return None


class AmazonTrackingRetriever(EmailTrackingRetriever):

  first_regex = r'.*href="(http[^"]*ship-?track[^"]*)"'
  second_regex = r'.*<a hr[^"]*=[^"]*"(http[^"]*progress-tracker[^"]*)"'
  price_regex = r'.*Shipment [Tt]otal: ?(\$[\d,]+\.\d{2})'
  order_ids_regex = r'(11\d-\d{7}-\d{7})'
  li_regex = re.compile(r"\d+\.\s+")

  def add_transferred_trackings(self, existing_trackings: List[Tracking],
                                new_trackings: Dict[str, Tracking]) -> None:
    print("Finding transferred trackings")
    mail = self.get_all_mail_folder()
    seen_filter = '(SEEN)' if self.args.seen else '(UNSEEN)'
    status, search_response = mail.uid('SEARCH', None, seen_filter,
                                       '(SUBJECT "We\'ve Transferred Your Amazon Package to UPS")')
    email_ids = search_response[0].decode('utf-8').split()
    if not email_ids:
      return
    failed_ids: List[str] = []
    for email_id in tqdm(email_ids, desc="Processing transfers", unit="email"):
      try:
        content = get_email_content(email_id, mail)
        order_id = re.findall(self.order_ids_regex, content)[0]
        new_tracking_number = re.findall('1Z[A-Z0-9]{16}', content)[0]
        old_tracking = find_old_tracking_by_order(order_id, existing_trackings, new_trackings)
        if not old_tracking:
          print(f"Couldn't find old tracking for order {order_id}, skipping")
          failed_ids.append(email_id)
        new_tracking = Tracking(new_tracking_number, old_tracking.group, {order_id},
                                old_tracking.price, old_tracking.to_email, old_tracking.ship_date,
                                old_tracking.tracked_cost, old_tracking.items,
                                old_tracking.merchant, old_tracking.reconcile,
                                old_tracking.delivery_date)
        new_trackings[new_tracking_number] = new_tracking
      except Exception as e:
        print(f"Exception when getting transferred tracking: {e}")
        failed_ids.append(email_id)
    if self.args.seen:
      self.mark_emails_as_unread(failed_ids)

  def get_order_url_from_email(self, raw_email):
    match = re.match(self.first_regex, str(raw_email))
    if not match:
      match = re.match(self.second_regex, str(raw_email))
    return match.group(1) if match else None

  def get_order_ids_from_email(self, raw_email):
    matches = re.findall(self.order_ids_regex, raw_email)
    return list(set(matches))

  def get_price_from_email(self, raw_email):
    # Price isn't necessary, so if we can't find it don't raise an exception
    match = re.match(self.price_regex, raw_email)
    if match:
      return match.group(1)
    return ''

  def get_subject_searches(self):
    return [["Your AmazonSmile order", "has shipped"], ["Your Amazon.com order", "has shipped"],
            ["Shipped: Now arriving early"]]

  def get_merchant(self) -> str:
    return "Amazon"

  def get_items_from_email(self, email_str):
    item_regex = r'(.*Qty: \d+)'
    soup = BeautifulSoup(email_str, features="html.parser")
    order_prefix_span = soup.find("span", {"class": "orderIdPrefix"})

    if not order_prefix_span:
      # grouped-order shipments don't have item breakdowns but they do have total-price, so use that
      return self.get_price_from_email(email_str)

    all_lis = order_prefix_span.find_all('li')

    item_descriptions = []
    for li in all_lis:
      txt = li.getText().strip()
      item_match = re.match(item_regex, txt)
      if item_match:
        item_descriptions.append(item_match.group(1))
    return ",".join(item_descriptions)

  def get_tracking_numbers_from_email(self, raw_email, from_email: str,
                                      to_email: str) -> List[Tuple[str, Optional[str]]]:
    url = self.get_order_url_from_email(raw_email)
    if not url:
      return []
    # First, attempt with the pre-existing not-logged-in driver
    attempt = self.get_tracking_info_logged_out(url, self.driver)
    if attempt or "profileBase" not in self.config:
      return attempt

    # If that fails, attempt to log in
    driver = self.find_login(to_email)
    if not driver:
      tqdm.write(f"Couldn't find profile directory for email: {to_email}")
      return []

    # Bulk ordering (from ship-confirm) or standard page (otherwise)
    if "ship-confirm@amazon.com" in from_email:
      return self.get_tracking_info_logged_in(url, driver)
    else:
      try:
        return self.get_tracking_info_logged_out(url, driver)
      finally:
        driver.quit()

  def find_login(self, to_email: str) -> Optional[WebDriver]:
    email_user = to_email.split("@")[0].lower()
    profile_base = self.config["profileBase"]
    # attempt exact matches first
    for profile_name in os.listdir(os.path.expanduser(profile_base)):
      if email_user == profile_name.lower():
        return new_driver(profile_base, profile_name)
    # then go to substrings
    for profile_name in os.listdir(os.path.expanduser(profile_base)):
      if email_user in profile_name.lower():
        return new_driver(profile_base, profile_name)
    return None

  def get_tracking_info_logged_in(self, amazon_url: str,
                                  driver: WebDriver) -> List[Tuple[str, Optional[str]]]:
    try:
      driver.get(amazon_url)
      shipment_eles = driver.find_elements_by_css_selector("div.a-section-expander-container")
      if len(shipment_eles) == 0:
        return self.get_trackings_within_shipment(
            driver,
            driver.find_element_by_css_selector(
                "div.a-col-left div.a-color-offset-background span.a-color-base").text.strip())
      else:
        trackings = []
        for shipment_ele in shipment_eles:
          delivery_status = shipment_ele.find_element_by_css_selector(
              "span.a-color-base").text.strip()
          shipment_ele.click()
          trackings.extend(self.get_trackings_within_shipment(shipment_ele, delivery_status))
        return trackings
    finally:
      driver.quit()

  def get_trackings_within_shipment(self, shipment_ele, delivery_status):
    trackings = []
    for item in shipment_ele.find_elements_by_css_selector("span[data-action='asinclick']"):
      item.click()
      for tracking in shipment_ele.find_elements_by_css_selector(
          "span[data-action='trackingidclick'] a.a-link-normal span.a-size-small"):
        trackings.append((self.li_regex.sub("", tracking.text.strip()), delivery_status))
    return trackings

  def get_tracking_info_logged_out(self, amazon_url: str,
                                   driver: WebDriver) -> List[Tuple[str, Optional[str]]]:
    self.load_url(driver, amazon_url)
    try:
      element = driver.find_element_by_xpath("//div[@class='pt-delivery-card-trackingId']")
      regex = r'Tracking ID: ([a-zA-Z0-9]+)'
      match = re.match(regex, element.text)
      if not match:
        return []
      tracking_number = match.group(1).upper()
      primary_status_elems = do_with_wait(driver, 2, 10,
                                          lambda: driver.find_elements_by_id('primaryStatus'))
      if primary_status_elems:
        shipping_status = primary_status_elems[0].get_attribute("textContent").strip(" \t\n\r")
      else:
        shipping_status = driver.find_element_by_css_selector(
          'section.promise-card h1.pt-promise-main-slot').text
      return [(tracking_number, shipping_status)]
    except:
      # swallow this and continue on
      return []

  def get_delivery_date_from_email(self, email_str):
    soup = BeautifulSoup(email_str, features="html.parser")
    critical_info = soup.find(id='criticalInfo')
    # biz email
    if critical_info:
      tds = critical_info.find_all('td')
      for i in range(max(2, len(tds))):
        date = _parse_date(tds[i].text)
        if date:
          return date
      return ''
    # personal email
    arrival_date_elem = soup.find(class_='arrivalDate')
    if not arrival_date_elem:
      return ''
    return _parse_date(arrival_date_elem.text)

  @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=120))
  def load_url(self, driver, url):
    driver.get(url)
    time.sleep(1)  # wait for page load because the timeouts can be buggy

  def log_in_if_necessary(self):
    driver = self.driver_creator.new()
    config = self.config
    driver.get('https://www.amazon.com/gp/your-account/order-history/ref=ppx_yo_dt_b_orders')
    if 'amazon' in config:
      print("Signing into Amazon ...")
      driver.find_element_by_css_selector('input[type="email"]').send_keys(config['amazon']['email'])
      driver.find_element_by_css_selector('input[type="submit"]').click()
      driver.find_element_by_css_selector('input[type="password"]').send_keys(config['amazon']['password'])
      driver.find_element_by_css_selector('input[type="submit"]').click()

      orders_containers = driver.find_elements_by_id('ordersContainer')
      if len(orders_containers) == 0:
        input('Enter your OTP on the opened Chrome profile. Hit ENTER when done.')
    else:
      input('Please log in to an Amazon account on the opened Chrome profile. Hit ENTER when done.')

    return driver
