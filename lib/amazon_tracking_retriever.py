import datetime
import re
import time
from typing import Tuple, Optional, List, Set

from selenium.webdriver.chrome.webdriver import WebDriver
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

from lib.email_tracking_retriever import EmailTrackingRetriever, AddressTrackingsAndOrders


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


def get_standard_orders(driver: WebDriver) -> Set[str]:
  container = driver.find_element_by_id('ordersInPackage-container')
  if 'orders in this package' not in container.text:
    return set()
  return set(re.findall(r'\d{3}-\d{7}-\d{7}', container.text))


def get_standard_trackings(driver: WebDriver) -> List[Tuple[str, Optional[str]]]:
  try:
    element = driver.find_element_by_xpath("//*[contains(text(), 'Tracking ID')]")
    regex = r'Tracking ID: ([a-zA-Z0-9]+)'
    match = re.match(regex, element.text)
    if not match:
      return []
    tracking_number = match.group(1).upper()
    shipping_status = driver.find_element_by_id("primaryStatus").get_attribute("textContent").strip(
        " \t\n\r")
    return [(tracking_number, shipping_status)]
  except:
    # swallow this and continue on
    return []


def get_standard_address_info(driver: WebDriver) -> str:
  shipping_address_containers = driver.find_elements_by_css_selector('div.a-row.shippingAddress')
  if not shipping_address_containers:
    raise Exception("Could not find shipping address container")
  return shipping_address_containers[0].text.strip()


def get_address_info_from_order_details_page(driver: WebDriver) -> str:
  display_address_divs = driver.find_elements_by_class_name('displayAddressDiv')
  if not display_address_divs:
    raise Exception("Could not find displayAddressDiv")
  return display_address_divs[0].text.strip()


class AmazonTrackingRetriever(EmailTrackingRetriever):

  first_regex = r'.*href="(http[^"]*ship-?track[^"]*)"'
  second_regex = r'.*<a hr[^"]*=[^"]*"(http[^"]*progress-tracker[^"]*)"'
  price_regex = r'.*Shipment [Tt]otal: ?(\$[\d,]+\.\d{2})'
  order_ids_regex = r'#(\d{3}-\d{7}-\d{7})'
  li_regex = re.compile(r"\d+\.\s+")

  def get_address_info_and_trackings(self, email_str: str, driver: Optional[WebDriver],
                                     from_email: str, to_email: str) -> AddressTrackingsAndOrders:
    if not driver:
      tqdm.write(f"No driver found for email {to_email}")
      return '', [], set()
    url = self.get_order_url_from_email(email_str)
    if not url:
      tqdm.write(f"No URL found for email addressed to {to_email}")
      return '', [], set()
    self.load_url(driver, url)
    # Bulk ordering (from ship-confirm) or standard page (otherwise)
    if "ship-confirm@amazon.com" in from_email:
      trackings = self.get_bulk_trackings(driver)
      # we have to grab the address from the order details page
      order_id = self.get_order_ids_from_email(email_str)[0]
      order_url = f"https://amazon.com/gp/your-account/order-details/ref=ppx_yo_dt_b_order_details_o03?ie=UTF8&orderID={order_id.strip()}"
      self.load_url(driver, order_url)
      address_info = get_address_info_from_order_details_page(driver)
      orders = set()
    else:
      trackings = get_standard_trackings(driver)
      address_info = get_standard_address_info(driver)
      orders = get_standard_orders(driver)
    return address_info, trackings, orders

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

  def get_bulk_trackings(self, driver: WebDriver) -> List[Tuple[str, Optional[str]]]:
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

  def get_trackings_within_shipment(self, shipment_ele, delivery_status):
    trackings = []
    for item in shipment_ele.find_elements_by_css_selector("span[data-action='asinclick']"):
      item.click()
      for tracking in shipment_ele.find_elements_by_css_selector(
          "div.asinTrackingInformation span.a-list-item span.a-size-small"):
        trackings.append((self.li_regex.sub("", tracking.text.strip()), delivery_status))
    return trackings

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
