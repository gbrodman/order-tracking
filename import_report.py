#!/usr/bin/env python3

import datetime
import lib.donations
import sys
import yaml
from lib.objects_to_sheet import ObjectsToSheet
from lib.tracking import Tracking
from lib.tracking_output import TrackingOutput
from typing import Any

CONFIG_FILE = "config.yml"
with open(CONFIG_FILE, 'r') as config_file_stream:
  config = yaml.safe_load(config_file_stream)


def get_group(header, row) -> Any:
  address = row[header.index("Shipping Address")]
  address = address.upper()
  for group in config['groups'].keys():
    group_keys = config['groups'][group]['keys']
    if isinstance(group_keys, str):
      group_keys = [group_keys]
    for group_key in group_keys:
      if str(group_key).upper() in address:
        return group
  return None


def from_amazon_row(header, row) -> Tracking:
  tracking = str(row[header.index('Carrier Tracking #')]).upper()
  orders = {row[header.index('Order ID')].upper()}
  price = float(
      str(row[header.index('Shipment Subtotal')]).replace(',', '').replace(
          '$', '').replace('N/A', '0.0'))
  to_email = row[header.index("Account User Email")]
  url = ''
  original_ship_date = str(row[header.index("Shipment Date")])
  try:
    ship_date = datetime.datetime.strptime(
        original_ship_date,
        "%m/%d/%Y").strftime("%Y-%m-%d") if original_ship_date != 'N/A' else ''
  except:
    ship_date = "n/a"
  group = get_group(header, row)
  tracked_cost = 0.0
  items = row[header.index("Title")] + " Qty:" + str(
      row[header.index("Item Quantity")])
  merchant = row[header.index('Merchant')] if 'Merchant' in header else 'Amazon'
  return Tracking(tracking, group, orders, price, to_email, url, ship_date,
                  tracked_cost, items, merchant)


def find_candidate(tracking, candidates) -> Any:
  for candidate in candidates:
    if tracking.tracking_number == candidate.tracking_number:
      return candidate
  return None


def dedupe_trackings(trackings) -> list:
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


def main(argv):
  sheet_id = get_required("Enter Google Sheet ID: ")
  tab_name = get_required("Enter the name of the tab within the sheet: ")
  objects_to_sheet = ObjectsToSheet()
  all_trackings = objects_to_sheet.download_from_sheet(from_amazon_row,
                                                       sheet_id, tab_name)
  all_trackings = [
      tracking for tracking in all_trackings
      if tracking.tracking_number != 'N/A' and tracking.tracking_number != ''
  ]
  all_trackings = dedupe_trackings(all_trackings)
  tracking_output = TrackingOutput()
  print("Number of trackings beforehand: %d" %
        len(tracking_output.get_existing_trackings(config)))
  print("Number from sheet: %d" % len(all_trackings))
  tracking_output.save_trackings(config, all_trackings)
  print("Number of trackings after: %d" %
        len(tracking_output.get_existing_trackings(config)))


if __name__ == "__main__":
  main(sys.argv)
