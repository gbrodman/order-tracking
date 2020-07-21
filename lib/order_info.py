import pickle
import os.path
import imaplib
import re
import quopri
import lib.email_auth as email_auth
from bs4 import BeautifulSoup
from lib.debounce import debounce
from lib.objects_to_drive import ObjectsToDrive
from typing import Any, Dict, Optional, Union

OUTPUT_FOLDER = "output"
ORDERS_FILENAME = "orders.pickle"
ORDERS_FILE = OUTPUT_FOLDER + "/" + ORDERS_FILENAME


class OrderInfo:
  """
  A value class that stores the information associated with a given order.

  Note that an order email can contain multiple orders within it if the order
  is broken up into multiple sub-orders at the time it is placed.
  """

  def __init__(self, email_id: str, cost: float) -> None:
    self.email_id = email_id
    self.cost = cost

  def __str__(self) -> str:
    return f'{{email_id: {self.email_id}, cost: {self.cost}}}'

  __repr__ = __str__


class OrderInfoRetriever:
  """
  A class that parses and stores the order numbers and email IDs for shipments.
  """

  def __init__(self, config) -> None:
    self.config = config
    self.orders_dict = self.load_dict()
    self.mail = self.load_mail()

  def load_mail(self):
    mail = email_auth.email_authentication()
    mail.select('"[Gmail]/All Mail"')
    return mail

  @debounce(5)
  def flush(self) -> None:
    if not os.path.exists(OUTPUT_FOLDER):
      os.mkdir(OUTPUT_FOLDER)

    with open(ORDERS_FILE, 'wb') as stream:
      pickle.dump(self.orders_dict, stream)

    objects_to_drive = ObjectsToDrive()
    objects_to_drive.save(self.config, ORDERS_FILENAME, ORDERS_FILE)

  def load_dict(self) -> Any:
    objects_to_drive = ObjectsToDrive()
    from_drive = objects_to_drive.load(self.config, ORDERS_FILENAME)
    if from_drive:
      return from_drive

    if not os.path.exists(ORDERS_FILE):
      return {}

    with open(ORDERS_FILE, 'rb') as stream:
      return pickle.load(stream)

  def get_order_info(self, order_id) -> OrderInfo:
    # Fetch the order from email if it's new or if we attempted to fetch it
    # previously but weren't able to find a cost (i.e. cost is still 0).
    if order_id not in self.orders_dict or self.orders_dict[order_id].cost == 0:
      from_email = self.load_order_total(order_id)
      if not from_email:
        from_email = {order_id: OrderInfo(None, 0.0)}
      self.orders_dict.update(from_email)
      self.flush()
    return self.orders_dict[order_id]

  def load_order_total(self, order_id: str) -> Dict[str, OrderInfo]:
    if order_id.startswith("BBY01"):
      return self.load_order_total_bb(order_id)
    else:
      return self.load_order_total_amazon(order_id)

  def load_order_total_bb(self, order_id: str) -> Dict[str, OrderInfo]:
    email_id, data = self.get_relevant_raw_email_data(order_id)
    if not data:
      print("Could not find email for order ID %s" % order_id)
      return {}

    raw_email = str(data[0][1])
    regex_subtotal = r'Subtotal[^\$]*\$([\d,]+\.[\d]{2})'
    regex_tax = r'Tax[^\$]*\$([\d,]+\.[\d]{2})'
    subtotal_match = re.search(regex_subtotal, raw_email)
    if not subtotal_match:
      return {}
    subtotal = float(subtotal_match.group(1).replace(',', ''))
    tax_match = re.search(regex_tax, raw_email)
    if not tax_match:
      return {}
    tax = float(tax_match.group(1).replace(',', ''))
    return {order_id: OrderInfo(email_id, subtotal + tax)}

  def load_order_total_amazon(self, order_id: str) -> Dict[str, OrderInfo]:
    email_id, data = self.get_relevant_raw_email_data(order_id)
    if not data:
      print("Could not find email for order ID %s" % order_id)
      return {}

    raw_email = str(data[0][1])
    regex_pretax = r'Total Before Tax:[^$]*\$([\d,]+\.\d{2})'
    regex_est_tax = r'Estimated Tax:[^$]*\$([\d,]+\.\d{2})'
    regex_order = r'(\d{3}-\d{7}-\d{7})'

    orders_with_duplicates = re.findall(regex_order, raw_email)
    orders = []
    for order in orders_with_duplicates:
      if order not in orders:
        orders.append(order)

    # Sometimes it's been split into multiple orders. Find totals for each
    pretax_totals = [float(cost.replace(',', '')) for cost in re.findall(regex_pretax, raw_email)]

    # personal emails might not have the regexes, need to do something different
    if not pretax_totals:
      return self.get_personal_amazon_totals(email_id, data, orders)

    taxes = [float(cost.replace(',', '')) for cost in re.findall(regex_est_tax, raw_email)]

    order_infos = [OrderInfo(email_id, t[0] + t[1]) for t in zip(pretax_totals, taxes)]
    return dict(zip(orders, order_infos))

  def get_relevant_raw_email_data(self, order_id) -> Union[str, Optional[str]]:
    status, search_result = self.mail.uid('SEARCH', None, 'BODY "%s"' % order_id)
    email_id = search_result[0]
    if not email_id:
      return None, None

    email_ids = search_result[0].decode('utf-8').split()
    if not email_ids:
      return None, None

    result, data = self.mail.uid("FETCH", email_ids[0], "(RFC822)")
    return email_ids[0], data

  def get_personal_amazon_totals(self, email_id, data, orders) -> Dict[str, OrderInfo]:
    soup = BeautifulSoup(
        quopri.decodestring(data[0][1]), features="html.parser", from_encoding="iso-8859-1")
    prices = [
        elem.getText().strip().replace(',', '').replace('$', '')
        for elem in soup.find_all('td', {"class": "price"})
    ]
    prices = [float(price) for price in prices if price]

    result = {}
    # prices alternate between pretax / tax
    for i in range(len(prices) // 2):
      total = prices[i * 2] + prices[i * 2 + 1]
      result[orders[i]] = OrderInfo(email_id, total)
    return result
