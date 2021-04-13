#!/usr/bin/env python3
import argparse
import concurrent
import csv
import datetime
import glob
import os
import time
from concurrent.futures.thread import ThreadPoolExecutor
from random import shuffle
from typing import Any, List, Optional, Callable, Dict, Tuple

from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.wait import WebDriverWait
from tqdm import tqdm

from lib import util
from lib.config import open_config
from lib.driver_creator import DriverCreator
from lib.group_site_manager import GroupSiteManager, clean_csv_tracking
from lib.objects_to_sheet import ObjectsToSheet
from lib.tracking import Tracking
from lib.tracking_output import TrackingOutput
from lib.tracking_uploader import TrackingUploader

config = open_config()
admin_profiles = config['adminProfiles']
shuffle(admin_profiles)
profile_base = config['profileBase']

ANALYTICS_URL = 'https://amazon.com/b2b/aba/'
PERSONAL_REPORT_URL = 'https://www.amazon.com/gp/b2b/reports'
REPORTS_DIR = os.path.join(os.getcwd(), 'reports')
MAX_WORKERS = 5
DOWNLOAD_TIMEOUT_SECS = 240


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


def do_with_spinner(driver, fn):
  fn()
  time.sleep(0.5)
  WebDriverWait(driver, 20).until(
      expected_conditions.invisibility_of_element_located((By.CSS_SELECTOR, "span.a-spinner")))


def create_driver(admin_profile: str, temp_dir: str) -> WebDriver:
  # Create temp dir to download this report into
  os.mkdir(temp_dir)
  return DriverCreator().new(
      user_data_dir=f"{os.path.expanduser(profile_base)}/{admin_profile}",
      download_dir=temp_dir,
      page_load=30)


def download_personal_report(driver: WebDriver) -> None:
  driver.get(PERSONAL_REPORT_URL)
  type_select = Select(driver.find_element_by_id('report-type'))
  type_select.select_by_visible_text('Orders and shipments')
  driver.execute_script('setDatesToYearToDate()')
  driver.find_element_by_id('report-confirm').click()


def download_shipping_report(driver: WebDriver) -> None:
  # Go to https://amazon.com/b2b/aba/
  driver.get(ANALYTICS_URL)
  # Click on Shipments link (thanks Amazon for the garbage-tier HTML)
  do_with_spinner(
      driver, lambda: driver.find_element_by_xpath("//a[span[span[text()='Shipments']]]").click())
  # Set Time period to "Past 12 months"
  driver.find_element_by_id("date_range_selector__range").click()
  do_with_spinner(driver,
                  lambda: driver.find_element_by_css_selector("a[value='PAST_12_MONTHS']").click())
  # Click "Download CSV"
  driver.find_element_by_id("download-csv-file-button").click()


def operate_on_profile(get_from_amazon_fn: Callable[[WebDriver], None], admin_profile: str,
                       report_dir: str) -> Optional[str]:
  temp_dir = os.path.join(report_dir, admin_profile)
  try:
    driver = create_driver(admin_profile, temp_dir)
  except Exception as e:
    tqdm.write(
        f"{admin_profile + ':':<20} Failed to open profile: {str(e)}\n{util.get_traceback_lines()}")
    return None
  try:
    get_from_amazon_fn(driver)
    for s in range(DOWNLOAD_TIMEOUT_SECS):
      dir_contents = os.listdir(temp_dir)
      if dir_contents and dir_contents[0].endswith(".csv"):  # Ignore .crdownload files
        file_path = os.path.join(temp_dir, dir_contents[0])
        kib = os.path.getsize(file_path) / 1024
        tqdm.write(
            f"{admin_profile + ':':<20} Successfully downloaded report ({kib:.0f} KiB in {s}s).")
        return file_path
      else:
        time.sleep(1)
    tqdm.write(f"{admin_profile + ':':<20} Failed: Downloading report timed out.")
  except Exception as e:
    tqdm.write(
        f"{admin_profile + ':':<20} Failed to fetch report: {str(e)}\n{util.get_traceback_lines()}")
    return None
  finally:
    driver.quit()


def download_reports_generic(get_from_amazon_fn: Callable[[WebDriver], None]):
  if not os.path.exists(REPORTS_DIR):
    os.mkdir(REPORTS_DIR)
  report_dir = os.path.join(REPORTS_DIR,
                            datetime.datetime.now().strftime("shipping_%Y-%m-%dT%H_%M_%S"))
  os.mkdir(report_dir)
  with ThreadPoolExecutor(MAX_WORKERS) as executor:
    tasks = {}
    report_paths = []
    for admin_profile in admin_profiles:
      tasks[executor.submit(operate_on_profile, get_from_amazon_fn, admin_profile,
                            report_dir)] = admin_profile
    for task in tqdm(
        concurrent.futures.as_completed(tasks),
        desc="Downloading reports",
        unit="profile",
        total=len(tasks),
        maxinterval=3):
      report_path = task.result()
      if report_path:
        report_paths.append(report_path)
    # Potential TODO: Retry failed imports.
    return report_paths


def download_az_personal_reports() -> List[str]:
  return download_reports_generic(download_personal_report)


def download_az_reports() -> List[str]:
  return download_reports_generic(download_shipping_report)


def read_trackings_from_file(file, from_row_fn: Callable[[Dict[str, str]],
                                                         Tracking]) -> List[Tracking]:
  with open(file, 'r') as f:
    reader = csv.DictReader(f)
    rows = [r for r in reader]
    return [from_row_fn(row) for row in rows]


def main():
  parser = argparse.ArgumentParser(description='Importing Amazon reports from CSV or Drive')
  parser.add_argument(
      "--download", "-d", action="store_true", help="Download from Amazon using logged-in profiles")
  parser.add_argument("--personal", "-p", action="store_true", help="Use the personal CSV format")
  parser.add_argument("globs", nargs="*")
  args, _ = parser.parse_known_args()

  all_trackings = []
  if args.download and not args.personal:
    files = download_az_reports()
    for file in files:
      all_trackings.extend(read_trackings_from_file(file, from_amazon_row))
  elif args.globs and not args.personal:
    for glob_input in args.globs:
      files = glob.glob(glob_input)
      for file in files:
        all_trackings.extend(read_trackings_from_file(file, from_amazon_row))
  elif args.download and args.personal:
    files = download_az_personal_reports()
    for file in files:
      all_trackings.extend(read_trackings_from_file(file, from_personal_row))
    pass
  elif args.globs and args.personal:
    for glob_input in args.globs:
      files = glob.glob(glob_input)
      for file in files:
        all_trackings.extend(read_trackings_from_file(file, from_personal_row))
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

  print("Uploading new trackings to the group(s)' site(s)...")
  group_site_manager = GroupSiteManager(config)
  group_site_manager.upload([trackings_after_save[t] for t in new_trackings])


if __name__ == "__main__":
  main()
