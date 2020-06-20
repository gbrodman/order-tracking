import datetime
import quopri
import re
import time
from typing import Tuple, Optional

from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from lib.email_tracking_retriever import EmailTrackingRetriever


class AmazonTrackingRetriever(EmailTrackingRetriever):

  first_regex = r'.*<a(?!href).*href="(http[^"]*ship-?track[^"]*)"'
  second_regex = r'.*<a hr[^"]*=[^"]*"(http[^"]*progress-tracker[^"]*)"'
  price_regex = r'.*Shipment total:(\$\d+\.\d{2})'
  order_ids_regex = r'#(\d{3}-\d{7}-\d{7})'

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
    return [["Your AmazonSmile order", "has shipped"], ["Your Amazon.com order", "has shipped"]]

  def get_merchant(self) -> str:
    return "Amazon"

  def get_items_from_email(self, data):
    item_regex = r'(.*Qty: \d+)'
    soup = BeautifulSoup(
        quopri.decodestring(data[0][1]), features="html.parser", from_encoding="iso-8859-1")
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

  def get_tracking_number_from_email(self, raw_email) -> Tuple[str, Optional[str]]:
    url = self.get_order_url_from_email(raw_email)
    if not url:
      return None, None
    return self.get_tracking_info(url)

  def get_tracking_info(self, amazon_url) -> Tuple[str, Optional[str]]:
    self.load_url(amazon_url)
    try:
      element = self.driver.find_element_by_xpath("//*[contains(text(), 'Tracking ID')]")
      regex = r'Tracking ID: ([a-zA-Z0-9]+)'
      match = re.match(regex, element.text)
      if not match:
        return None, None
      tracking_number = match.group(1).upper()
      shipping_status = self.driver.find_element_by_id("primaryStatus").get_attribute(
          "textContent").strip(" \t\n\r")
      return tracking_number, shipping_status
    except:
      # swallow this and continue on
      return None, None

  def get_delivery_date_from_email(self, data):
    soup = BeautifulSoup(
        quopri.decodestring(data[0][1]), features="html.parser", from_encoding="iso-8859-1")
    text = self.get_date_text_from_soup(soup)
    if not text:
      return ''
    date_text = text.split(',')[-1].strip()
    date_text = ' '.join(date_text.split(' ')[0:2])
    try:
      date = datetime.datetime.strptime(date_text,
                                        "%B %d").replace(year=datetime.datetime.now().year)
      return date.strftime('%Y-%m-%d')
    except:
      return ''

  def get_date_text_from_soup(self, soup):
    critical_info = soup.find(id='criticalInfo')
    # biz email
    if critical_info:
      tds = critical_info.find_all('td')
      if len(tds) < 2:
        return ''
      return tds[1].text
    # personal email
    arrival_date_elem = soup.find(class_='arrivalDate')
    if not arrival_date_elem:
      return ''
    return arrival_date_elem.text

  @retry(stop=stop_after_attempt(7), wait=wait_exponential(multiplier=1, min=2, max=120))
  def load_url(self, url):
    self.driver.get(url)
    time.sleep(1)  # wait for page load because the timeouts can be buggy
