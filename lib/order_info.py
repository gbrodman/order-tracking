import re

from tqdm import tqdm

import lib.email_auth as email_auth
from bs4 import BeautifulSoup

from lib import email_tracking_retriever
from lib.debounce import debounce
from lib.object_retriever import ObjectRetriever
from typing import Dict, Optional, Tuple
from math import isclose

ORDERS_FILENAME = "orders.pickle"

MISSING_COST_SENTINEL = 123456.78


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
    self.retriever = ObjectRetriever(config)
    self.orders_dict = self.retriever.load(ORDERS_FILENAME)
    self.mail = self.load_mail()

  def load_mail(self):
    mail = email_auth.email_authentication()
    mail.select('"[Gmail]/All Mail"')
    return mail

  @debounce(5)
  def flush(self) -> None:
    self.retriever.flush(self.orders_dict, ORDERS_FILENAME)

  def get_order_info(self, order_id, fetch_from_email: bool = True) -> OrderInfo:
    # Always fetch if we've never seen this order before, additionally fetch iff
    # we found a 0 or MISSING_COST_SENTINEL cost before and we want to retry.
    if order_id not in self.orders_dict or (
        fetch_from_email and (self.orders_dict[order_id].cost == 0 or
                              isclose(self.orders_dict[order_id].cost, MISSING_COST_SENTINEL))):
      from_email = self.load_order_total(order_id)
      if not from_email:
        from_email = {order_id: OrderInfo(None, MISSING_COST_SENTINEL)}
      self.orders_dict.update(from_email)
      self.flush()
    return self.orders_dict[order_id]

  def load_order_total(self, order_id: str) -> Dict[str, OrderInfo]:
    if order_id.startswith("BBY01"):
      return self.load_order_total_bb(order_id)
    else:
      return self.load_order_total_amazon(order_id)

  def load_order_total_bb(self, order_id: str) -> Dict[str, OrderInfo]:
    email_id, email_str = self.get_relevant_raw_email_data(order_id)
    if not email_str:
      print("Could not find email for order ID %s" % order_id)
      return {}

    regex_subtotal = r'Subtotal[^\$]*\$([\d,]+\.[\d]{2})'
    regex_tax = r'Tax[^\$]*\$([\d,]+\.[\d]{2})'
    subtotal_match = re.search(regex_subtotal, email_str)
    if not subtotal_match:
      return {}
    subtotal = float(subtotal_match.group(1).replace(',', ''))
    tax_match = re.search(regex_tax, email_str)
    if not tax_match:
      return {}
    tax = float(tax_match.group(1).replace(',', ''))
    return {order_id: OrderInfo(email_id, subtotal + tax)}

  def load_order_total_amazon(self, order_id: str) -> Dict[str, OrderInfo]:
    email_id, email_str = self.get_relevant_raw_email_data(order_id)
    if not email_str:
      tqdm.write(f"Could not find email for order ID {order_id}.")
      return {}

    regex_pretax = r'Total Before Tax:[^$]*\$([\d,]+\.\d{2})'
    regex_est_tax = r'Estimated Tax:[^$]*\$([\d,]+\.\d{2})'
    regex_order_total = r'Order Total:[^$]*\$([\d,]+\.\d{2})'
    regex_order = r'(\d{3}-\d{7}-\d{7})'

    orders_with_duplicates = re.findall(regex_order, email_str)
    orders = []
    for order in orders_with_duplicates:
      if order not in orders:
        orders.append(order)

    # Sometimes it's been split into multiple orders. Find totals for each
    pretax_totals = [float(cost.replace(',', '')) for cost in re.findall(regex_pretax, email_str)]

    if pretax_totals:
      taxes = [float(cost.replace(',', '')) for cost in re.findall(regex_est_tax, email_str)]
      order_infos = [OrderInfo(email_id, t[0] + t[1]) for t in zip(pretax_totals, taxes)]
      return dict(zip(orders, order_infos))
    else:
      # personal emails might not have the regexes, need to do something different
      personal_result = self.get_personal_amazon_totals(email_id, email_str, orders)
      if personal_result:
        return personal_result
      else:
        # amazon sometimes uses a new, odd format that only shows a single order total
        overall_totals = [
            float(cost.replace(',', '')) for cost in re.findall(regex_order_total, email_str)
        ]
        order_infos = [OrderInfo(email_id, t) for t in overall_totals]
        return dict(zip(orders, order_infos))

  def get_relevant_raw_email_data(self, order_id) -> Tuple[Optional[str], Optional[str]]:
    status, search_result = self.mail.uid('SEARCH', None, f'BODY "Order #{order_id}"', 'FROM "auto-confirm@amazon.com"')
    email_id = search_result[0]
    if not email_id:
      return None, None

    email_ids = search_result[0].decode('utf-8').split()
    if not email_ids:
      return None, None

    email_str = email_tracking_retriever.get_email_content(email_ids[0], self.mail)
    email_str = email_str.replace('\r\n', '')
    return email_ids[0], email_str

  def get_personal_amazon_totals(self, email_id, email_str, orders) -> Dict[str, OrderInfo]:
    soup = BeautifulSoup(email_str, features="html.parser")
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
