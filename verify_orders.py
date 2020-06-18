import argparse
import lib.email_auth as email_auth
import datetime

from functools import cmp_to_key

from lib.amazon_tracking_retriever import AmazonTrackingRetriever
from lib.cancelled_items_retriever import CancelledItemsRetriever
from lib.config import open_config
from lib.email_tracking_retriever import EmailTrackingRetriever
from lib.objects_to_sheet import ObjectsToSheet
from lib.tracking import convert_int_to_date
from lib.tracking_output import TrackingOutput

from tqdm import tqdm


class Order:

  def __init__(self, order_id, date, to_email, manually_verified):
    self.order_id = order_id
    self.date = date
    self.to_email = to_email
    self.manually_verified = manually_verified

  def to_row(self):
    return [self.order_id, self.date, self.to_email, self.manually_verified]

  def get_header(self):
    return ['Order ID', 'Date', 'To Email', 'Manually Verified']


def order_from_row(header, row):
  order_id = str(row[header.index('Order ID')])
  date = row[header.index("Date")]
  if isinstance(date, int):
    date = convert_int_to_date(date)
  to_email = str(row[header.index('To Email')])
  manually_verified = row[header.index('Manually Verified')]
  return Order(order_id, date, to_email, manually_verified)


def get_email_ids(mail, args):
  lookback_days = int(args.days) if args.days else 90
  date = datetime.date.today() - datetime.timedelta(days=lookback_days)
  date_to_search = date.strftime("%d-%b-%Y")
  status, response = mail.uid('SEARCH', None, f'(SINCE "{date_to_search}")',
                              '(FROM "auto-confirm@amazon.com")')
  return response[0].decode('utf-8').split()


def get_order_ids_to_orders(args):
  mail = email_auth.email_authentication()
  mail.select('"[Gmail]/All Mail"')
  email_ids = get_email_ids(mail, args)

  result = {}
  for email_id in tqdm(email_ids, desc="Fetching orders", unit="email"):
    _, data = mail.uid("FETCH", email_id, "(RFC822)")
    date = EmailTrackingRetriever.get_date_from_msg(None, data)
    to_email = EmailTrackingRetriever.get_to_address(None, data)

    raw_email = str(data[0][1]).replace("=3D", "=").replace('=\\r\\n',
                                                            '').replace('\\r\\n',
                                                                        '').replace('&amp;', '&')
    order_ids = AmazonTrackingRetriever.get_order_ids_from_email(AmazonTrackingRetriever, raw_email)
    for order_id in order_ids:
      result[order_id] = Order(order_id, date, to_email, False)
  return result


def get_orders_from_sheet(sheet_id):
  objects_to_sheet = ObjectsToSheet()
  return objects_to_sheet.download_from_sheet(order_from_row, sheet_id, 'Non-Shipped Orders')


def filter_orders(orders_list, config):
  tracking_output = TrackingOutput(config)
  seen_order_ids = set()
  for tracking in tracking_output.get_existing_trackings():
    seen_order_ids.update(tracking.order_ids)

  cancelled_items_retriever = CancelledItemsRetriever(config)
  cancellations_by_order = cancelled_items_retriever.get_cancelled_items()

  result = []
  for order in orders_list:
    if order.order_id not in seen_order_ids and order.order_id not in cancellations_by_order:
      result.append(order)

  return result


def compare(order_one, order_two) -> int:
  # manually verified ones come last
  if order_two.manually_verified and not order_one.manually_verified:
    return -1
  elif order_one.manually_verified and not order_two.manually_verified:
    return 1
  # next use dates
  elif order_one.date < order_two.date:
    return -1
  elif order_one.date == order_two.date:
    return 0
  else:
    return 1


def main():
  parser = argparse.ArgumentParser(
      description="Ouptut a set of orders for which we don't have shipments")
  parser.add_argument("--days")
  args, _ = parser.parse_known_args()

  order_ids_to_orders = get_order_ids_to_orders(args)
  config = open_config()
  sheet_id = config['reconciliation']['baseSpreadsheetId']
  orders_from_sheet = get_orders_from_sheet(sheet_id)

  for previous_order in orders_from_sheet:
    if previous_order.manually_verified and previous_order.order_id in order_ids_to_orders:
      order_ids_to_orders[previous_order.order_id].manually_verified = True

  orders_list = list(order_ids_to_orders.values())

  orders_list = filter_orders(orders_list, config)
  orders_list.sort(key=cmp_to_key(compare))

  objects_to_sheet = ObjectsToSheet()
  objects_to_sheet.upload_to_sheet(orders_list, sheet_id, 'Non-Shipped Orders')


if __name__ == '__main__':
  main()
