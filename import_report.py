#!/usr/bin/env python3
import argparse
import csv
import datetime
import glob
from typing import List, Optional, Callable, Dict, Tuple

from lib.config import open_config
from lib.driver_creator import DriverCreator
from lib.email_sender import EmailSender
from lib.group_site_manager import GroupSiteManager, clean_csv_tracking
from lib.objects_to_sheet import ObjectsToSheet
from lib.tracking import Tracking
from lib.tracking_output import TrackingOutput
from lib.tracking_uploader import TrackingUploader

config = open_config()


def get_group(address: str) -> Tuple[Optional[str], bool]:
  address = address.upper()
  for group in config['groups'].keys():
    group_conf = config['groups'][group]
    reconcile = bool(group_conf['reconcile']) if 'reconcile' in group_conf else True
    group_keys = config['groups'][group]['keys']
    if isinstance(group_keys, str):
      group_keys = [group_keys]
    for group_key in group_keys:
      if str(group_key).upper() in address:
        return group, reconcile
  if len(address) > 3:
    print(f"No group from address {address}:")
  return None, True


def get_ship_date(ship_date_str: str) -> str:
  for date_format in ['%m/%d/%Y', '%m/%d/%y']:
    try:
      ship_date = datetime.datetime.strptime(ship_date_str, date_format)
      return ship_date.strftime('%Y-%m-%d')
    except:
      pass
  try:
    return (datetime.date(year=1899, day=29, month=12) +
            datetime.timedelta(days=int(ship_date_str))).strftime('%Y-%m-%d')
  except:
    return 'n/a'


def from_amazon_row(row: Dict[str, str]) -> Optional[Tracking]:
  tracking = clean_csv_tracking(row['Carrier Tracking #'])
  orders = {row['Order ID'].upper()}
  price_str = str(row['Shipment Subtotal']).replace(',', '').replace('$', '').replace('N/A', '0.0')
  price = float(price_str) if price_str else 0.0
  to_email = row["Account User Email"]
  ship_date = get_ship_date(str(row["Shipment Date"]))
  group, reconcile = get_group(row['Shipping Address'])
  if group is None:
    return None
  tracked_cost = 0.0
  items = row["Title"] + " Qty:" + str(row["Item Quantity"])
  merchant = row['Merchant'] if 'Merchant' in row else 'Amazon'
  return Tracking(
      tracking,
      group,
      orders,
      price,
      to_email,
      ship_date=ship_date,
      tracked_cost=tracked_cost,
      items=items,
      merchant=merchant,
      reconcile=reconcile)


def from_personal_row(row: Dict[str, str]) -> Optional[Tracking]:
  tracking_col = row['Carrier Name & Tracking Number']
  if not tracking_col:
    return None
  tracking = tracking_col.split('(')[1].replace(')', '')
  orders = {row['Order ID'].upper()}
  price_str = str(row['Subtotal']).replace(',', '').replace('$', '').replace('N/A', '0.0')
  price = float(price_str) if price_str else 0.0
  to_email = row['Ordering Customer Email']
  ship_date = get_ship_date(str(row["Shipment Date"]))
  street_1 = row['Shipping Address Street 1']
  city = row['Shipping Address City']
  state = row['Shipping Address State']
  address = f"{street_1} {city}, {state}"
  group, reconcile = get_group(address)
  if group is None:
    return None
  tracked_cost = 0.0
  items = price_str
  merchant = 'Amazon'
  return Tracking(
      tracking,
      group,
      orders,
      price,
      to_email,
      ship_date=ship_date,
      tracked_cost=tracked_cost,
      items=items,
      merchant=merchant,
      reconcile=reconcile)


def find_candidate(tracking, candidates) -> Optional[Tracking]:
  for candidate in candidates:
    if tracking.tracking_number == candidate.tracking_number:
      return candidate
  return None


def dedupe_trackings(trackings: List[Tracking]) -> List[Tracking]:
  result = []
  for tracking in trackings:
    candidate = find_candidate(tracking, result)
    if candidate:
      candidate.order_ids = set(candidate.order_ids)
      candidate.order_ids.update(tracking.order_ids)
      if candidate.price:
        candidate.price = float(candidate.price) + tracking.price
      candidate.items += "," + tracking.items
    else:
      result.append(tracking)
  return result


def get_required(prompt):
  result = ""
  while not result:
    result = str(input(prompt)).strip()
  return result


def read_trackings_from_file(file, from_row_fn: Callable[[Dict[str, str]],
                                                         Tracking]) -> List[Tracking]:
  with open(file, 'r') as f:
    reader = csv.DictReader(f)
    rows = [r for r in reader]
    return [from_row_fn(row) for row in rows]


def main():
  parser = argparse.ArgumentParser(description='Importing Amazon reports from CSV or Drive')
  parser.add_argument("--personal", "-p", action="store_true", help="Use the personal CSV format")
  parser.add_argument("globs", nargs="*")
  args, _ = parser.parse_known_args()

  from_row_function = from_personal_row if args.personal else from_amazon_row
  all_trackings = []
  if args.globs:
    for glob_input in args.globs:
      files = glob.glob(glob_input)
      for file in files:
        all_trackings.extend(read_trackings_from_file(file, from_row_function))
  else:
    sheet_id = get_required("Enter Google Sheet ID: ")
    tab_name = get_required("Enter the name of the tab within the sheet: ")
    objects_to_sheet = ObjectsToSheet()
    all_trackings.extend(objects_to_sheet.download_from_sheet(from_amazon_row, sheet_id, tab_name))

  if len(all_trackings) == 0:
    print("Nothing to import; terminating.")
    return

  num_n_a_trackings = len(
      [ignored for ignored in all_trackings if ignored and ignored.tracking_number == 'N/A'])
  num_empty_trackings = len(
      [ignored for ignored in all_trackings if ignored and ignored.tracking_number == ''])
  print(f'Skipping {num_n_a_trackings} for N/A tracking column and '
        f'{num_empty_trackings} for empty tracking column.')
  all_trackings = [
      tracking for tracking in all_trackings
      if tracking and tracking.tracking_number != 'N/A' and tracking.tracking_number != ''
  ]
  len_non_reconcilable_trackings = len([t for t in all_trackings if not t.reconcile])
  print(f'Skipping {len_non_reconcilable_trackings} non-reconcilable trackings.')
  all_trackings = [t for t in all_trackings if t.reconcile]
  base_len_trackings = len(all_trackings)
  all_trackings = dedupe_trackings(all_trackings)
  print(f'Filtered {base_len_trackings - len(all_trackings)} duplicate trackings from the sheet.')

  print('Uploading trackings to Sheets...')
  tracking_uploader = TrackingUploader(config)
  tracking_uploader.upload_trackings(all_trackings)

  tracking_output = TrackingOutput(config)
  trackings_before_save = {t.tracking_number for t in tracking_output.get_existing_trackings()}
  print(f"Number of trackings before: {len(trackings_before_save)}.")
  print(f"Number imported from report(s): {len(all_trackings)}.")
  tracking_output.save_trackings(all_trackings)
  trackings_after_save = {t.tracking_number: t for t in tracking_output.get_existing_trackings()}
  print(f"Number of trackings after: {len(trackings_after_save)}.")
  new_trackings = set(trackings_after_save.keys()).difference(trackings_before_save)
  print(f"Number of new-to-us trackings: {len(new_trackings)}")

  new_tracking_objects = [trackings_after_save[t] for t in new_trackings]
  email_config = config['email']
  email_sender = EmailSender(email_config)
  email_sender.send_email(new_tracking_objects)

  print("Uploading new trackings to the group(s)' site(s)...")
  group_site_manager = GroupSiteManager(config, DriverCreator())
  group_site_manager.upload(new_tracking_objects)


if __name__ == "__main__":
  main()
