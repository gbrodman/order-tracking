import quopri
import re
import time
from bs4 import BeautifulSoup
from email_tracking_retriever import EmailTrackingRetriever
from tracking import Tracking


class AmazonTrackingRetriever(EmailTrackingRetriever):

  first_regex = r'.*<a href="(http[^"]*ship-?track[^"]*)"'
  second_regex = r'.*<a hr[^"]*=[^"]*"(http[^"]*progress-tracker[^"]*)"'
  price_regex = r'.*Shipment total:(\$\d+\.\d{2})'
  order_ids_regex = r'#(\d{3}-\d{7}-\d{7})'

  def get_order_url_from_email(self, raw_email):
    match = re.match(self.first_regex, str(raw_email))
    if not match:
      match = re.match(self.second_regex, str(raw_email))
    if match:
      return match.group(1)
    print(raw_email)
    raise Exception("Could not get URL from email")

  def get_order_ids_from_email(self, raw_email):
    matches = re.findall(self.order_ids_regex, raw_email)
    return list(set(matches))

  def get_price_from_email(self, raw_email):
    # Price isn't necessary, so if we can't find it don't raise an exception
    match = re.match(self.price_regex, raw_email)
    if match:
      return match.group(1)
    return ''

  def get_from_email_address(self):
    return "shipment-tracking@amazon.com"

  def get_items_from_email(self, data):
    item_regex = r'(.*Qty: \d+)'
    soup = BeautifulSoup(
        quopri.decodestring(data[0][1]), features="html.parser")
    order_prefix_span = soup.find("span", {"class": "orderIdPrefix"})

    if not order_prefix_span:
      return ''

    all_lis = order_prefix_span.find_all('li')

    item_descriptions = []
    for li in all_lis:
      txt = li.getText().strip()
      item_match = re.match(item_regex, txt)
      if item_match:
        item_descriptions.append(item_match.group(1))
    return ",".join(item_descriptions)

  def get_tracking_number_from_email(self, raw_email):
    url = self.get_order_url_from_email(raw_email)
    return self.get_tracking_info(url)

  def get_tracking_info(self, amazon_url):
    driver = self.load_url(amazon_url)
    try:
      element = driver.find_element_by_xpath(
          "//*[contains(text(), 'Tracking ID')]")
      regex = r'Tracking ID: ([a-zA-Z0-9]+)'
      match = re.match(regex, element.text)
      if not match:
        return None
      tracking_number = match.group(1)
      return tracking_number.upper()
    except:
      # swallow this and continue on
      return None
    finally:
      driver.close()

  def load_url(self, url):
    driver = self.driver_creator.new()
    driver.get(url)
    time.sleep(3)  # wait for page load because the timeouts can be buggy
    return driver
