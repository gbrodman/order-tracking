import pickle
import os.path
import imaplib
import re
import quopri
from bs4 import BeautifulSoup
from lib.objects_to_drive import ObjectsToDrive
from typing import Any, Dict, Optional, TypeVar

_T0 = TypeVar('_T0')

OUTPUT_FOLDER = "output"
COSTS_FILENAME = "expected_costs.pickle"
COSTS_FILE = OUTPUT_FOLDER + "/" + COSTS_FILENAME


class ExpectedCosts:

  def __init__(self, config) -> None:
    self.config = config
    self.costs_dict = self.load_dict()

  def flush(self) -> None:
    if not os.path.exists(OUTPUT_FOLDER):
      os.mkdir(OUTPUT_FOLDER)

    with open(COSTS_FILE, 'wb') as stream:
      pickle.dump(self.costs_dict, stream)

    objects_to_drive = ObjectsToDrive()
    objects_to_drive.save(self.config, COSTS_FILENAME, COSTS_FILE)

  def load_dict(self) -> Any:
    objects_to_drive = ObjectsToDrive()
    from_drive = objects_to_drive.load(self.config, COSTS_FILENAME)
    if from_drive:
      return from_drive

    if not os.path.exists(COSTS_FILE):
      return {}

    with open(COSTS_FILE, 'rb') as stream:
      return pickle.load(stream)

  def get_expected_cost(self, order_id) -> Any:
    if order_id not in self.costs_dict or not self.costs_dict[order_id]:
      print("Getting cost for order_id %s" % order_id)
      from_email = self.load_order_total(order_id)
      from_email = from_email if from_email else {order_id: 0.0}
      self.costs_dict.update(from_email)
      self.flush()
    return self.costs_dict[order_id]

  def load_order_total(self, order_id: _T0) -> dict:
    if order_id.startswith("BBY01"):
      return self.load_order_total_bb(order_id)
    else:
      return self.load_order_total_amazon(order_id)

  def load_order_total_bb(self, order_id: _T0) -> Dict[_T0, float]:
    data = self.get_relevant_raw_email_data(order_id)
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
    return {order_id: subtotal + tax}

  def load_order_total_amazon(self, order_id: _T0) -> Dict[_T0, float]:
    data = self.get_relevant_raw_email_data(order_id)
    if not data:
      print("Could not find email for order ID %s" % order_id)
      return {}

    raw_email = str(data[0][1])
    regex_pretax = r'Total Before Tax:\s*\$([\d,]+\.\d{2})'
    regex_est_tax = r'Estimated Tax:\s*\$([\d,]+\.\d{2})'
    regex_order = r'(\d{3}-\d{7}-\d{7})'

    orders_with_duplicates = re.findall(regex_order, raw_email)
    orders = []
    for order in orders_with_duplicates:
      if order not in orders:
        orders.append(order)

    # Sometimes it's been split into multiple orders. Find totals for each
    pretax_totals = [
        float(cost.replace(',', ''))
        for cost in re.findall(regex_pretax, raw_email)
    ]

    # personal emails might not have the regexes, need to do something different
    if not pretax_totals:
      return self.get_personal_amazon_totals(data, orders)

    taxes = [
        float(cost.replace(',', ''))
        for cost in re.findall(regex_est_tax, raw_email)
    ]

    order_totals = [t[0] + t[1] for t in zip(pretax_totals, taxes)]
    return dict(zip(orders, order_totals))

  def get_relevant_raw_email_data(self, order_id) -> Optional[str]:
    mail = imaplib.IMAP4_SSL(self.config['email']['imapUrl'])
    mail.login(self.config['email']['username'],
               self.config['email']['password'])
    mail.select('"[Gmail]/All Mail"')

    status, search_result = mail.uid('SEARCH', None, 'BODY "%s"' % order_id)
    email_id = search_result[0]
    if not email_id:
      return None

    email_ids = search_result[0].decode('utf-8').split()
    if not email_ids:
      return None

    result, data = mail.uid("FETCH", email_ids[0], "(RFC822)")
    return data

  def get_personal_amazon_totals(self, data, orders):
    soup = BeautifulSoup(
        quopri.decodestring(data[0][1]), features="html.parser")
    prices = [
        elem.getText().strip().replace(',', '').replace('$', '')
        for elem in soup.find_all('td', {"class": "price"})
    ]
    prices = [float(price) for price in prices if price]

    result = {}
    # prices alternate between pretax / tax
    for i in range(len(prices) // 2):
      total = prices[i * 2] + prices[i * 2 + 1]
      result[orders[i]] = total
    return result
