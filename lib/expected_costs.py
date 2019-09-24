import pickle
import os.path
import imaplib
import re
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

    if 'driveFolderId' in self.config:
      objects_to_drive = ObjectsToDrive()
      objects_to_drive.save(self.config['driveFolderId'], COSTS_FILENAME,
                            COSTS_FILE)

  def load_dict(self) -> Any:
    if 'driveFolderId' in self.config:
      objects_to_drive = ObjectsToDrive()
      from_drive = objects_to_drive.load(self.config['driveFolderId'],
                                         COSTS_FILENAME)
      if from_drive:
        return from_drive

    if not os.path.exists(COSTS_FILE):
      return {}

    with open(COSTS_FILE, 'rb') as stream:
      return pickle.load(stream)

  def get_expected_cost(self, order_id) -> Any:
    print("Getting cost for order_id %s" % order_id)
    if order_id not in self.costs_dict:
      from_email = self.load_order_total(order_id)
      self.costs_dict.update(from_email)
      self.flush()
    return self.costs_dict[order_id]

  def load_order_total(self, order_id: _T0) -> dict:
    if order_id.startswith("BBY01"):
      return self.load_order_total_bb(order_id)
    else:
      return self.load_order_total_amazon(order_id)

  def load_order_total_bb(self, order_id: _T0) -> Dict[_T0, float]:
    raw_email = self.get_relevant_raw_email("BestBuyInfo@emailinfo.bestbuy.com",
                                            order_id)
    regex_subtotal = r'Subtotal[^\$]*\$([\d,]+\.[\d]{2})'
    regex_tax = r'Tax[^\$]*\$([\d,]+\.[\d]{2})'
    subtotal_match = re.search(regex_subtotal, raw_email)
    if not subtotal_match:
      return {order_id: 0.0}
    subtotal = float(subtotal_match.group(1).replace(',', ''))
    tax_match = re.search(regex_tax, raw_email)
    if not tax_match:
      return {order_id: 0.0}
    tax = float(tax_match.group(1).replace(',', ''))
    return {order_id: subtotal + tax}

  def load_order_total_amazon(self, order_id: _T0) -> Dict[_T0, float]:
    raw_email = self.get_relevant_raw_email("auto-confirm@amazon.com", order_id)
    if not raw_email:
      return {order_id: 0.0}

    regex_pretax = r'Total Before Tax: \$([\d,]+\.\d{2})'
    regex_est_tax = r'Estimated Tax: \$([\d,]+\.\d{2})'
    regex_order = r'(\d{3}-\d{7}-\d{7})'

    # Sometimes it's been split into multiple orders. Find totals for each
    pretax_totals = [
        float(cost.replace(',', ''))
        for cost in re.findall(regex_pretax, raw_email)
    ]
    taxes = [
        float(cost.replace(',', ''))
        for cost in re.findall(regex_est_tax, raw_email)
    ]
    orders_with_duplicates = re.findall(regex_order, raw_email)
    orders = []
    for order in orders_with_duplicates:
      if order not in orders:
        orders.append(order)

    order_totals = [t[0] + t[1] for t in zip(pretax_totals, taxes)]
    return dict(zip(orders, order_totals))

  def get_relevant_raw_email(self, from_address, order_id) -> Optional[str]:
    mail = imaplib.IMAP4_SSL(self.config['email']['imapUrl'])
    mail.login(self.config['email']['username'],
               self.config['email']['password'])
    mail.select('"[Gmail]/All Mail"')

    status, search_result = mail.uid('SEARCH', None, 'FROM "%s"' % from_address,
                                     'BODY "%s"' % order_id)
    email_id = search_result[0]
    if not email_id:
      return None

    email_ids = search_result[0].decode('utf-8').split()

    result, data = mail.uid("FETCH", email_ids[0], "(RFC822)")
    return str(data[0][1])
