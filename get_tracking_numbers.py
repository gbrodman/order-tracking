#!/usr/bin/env python3
#
# Run this script to pick up new tracking numbers from unread shipping
# notification emails.
#
# Optional parameters:
#   --seen    Re-process already read emails.
#   --days N  Set the lookback period to N days instead of using the configured
#             value.

import argparse
import lib.donations
import sys
import traceback
import yaml
from lib.amazon_tracking_retriever import AmazonTrackingRetriever
from lib.bestbuy_tracking_retriever import BestBuyTrackingRetriever
from lib.driver_creator import DriverCreator
from lib.email_sender import EmailSender
from lib.group_site_manager import GroupSiteManager
from lib.tracking_uploader import TrackingUploader
from lib.tracking_output import TrackingOutput

CONFIG_FILE = "config.yml"


def send_error_email(email_sender, subject):
  type, value, trace = sys.exc_info()
  formatted_trace = traceback.format_tb(trace)
  lines = [str(type), str(value)] + formatted_trace
  email_sender.send_email_content(subject, "\n".join(lines))


def main():
  parser = argparse.ArgumentParser(description='Get tracking #s script')
  parser.add_argument("--seen", action="store_true")
  parser.add_argument("--days")
  args, _ = parser.parse_known_args()

  driver_creator = DriverCreator()

  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)
  email_config = config['email']
  email_sender = EmailSender(email_config)

  print("Retrieving Amazon tracking numbers from email...")
  amazon_tracking_retriever = AmazonTrackingRetriever(config, args,
                                                      driver_creator)
  try:
    trackings = amazon_tracking_retriever.get_trackings()
  except:
    send_error_email(email_sender, "Error retrieving Amazon emails")
    raise

  action_taken = "" if args.seen else " and marked them as unread"
  if amazon_tracking_retriever.failed_email_ids:
    print(
        f"Found {len(amazon_tracking_retriever.failed_email_ids)} Amazon emails "
        f"without buying group labels{action_taken}. Continuing...")

  print("Retrieving Best Buy tracking numbers from email...")
  bestbuy_tracking_retriever = BestBuyTrackingRetriever(config, args,
                                                        driver_creator)
  try:
    trackings.update(bestbuy_tracking_retriever.get_trackings())
  except:
    send_error_email(email_sender, "Error retrieving BB emails")
    raise

  if bestbuy_tracking_retriever.failed_email_ids:
    print(
        f"Found {len(bestbuy_tracking_retriever.failed_email_ids)} Best Buy emails "
        f"without buying group labels{action_taken}. Continuing...")

  try:
    tracking_output = TrackingOutput(config)
    existing_tracking_nos = set(
        [t.tracking_number for t in tracking_output.get_existing_trackings()])
    new_tracking_nos = set(trackings.keys()).difference(existing_tracking_nos)
    print(f"Found {len(new_tracking_nos)} new tracking numbers "
          f"(out of {len(trackings)} total) from emails.")
    new_trackings = [trackings[n] for n in new_tracking_nos]

    # We only need to process and upload new tracking numbers if there are any;
    # otherwise skip straight to processing existing locally stored data.
    if new_trackings:
      email_sender.send_email(new_trackings)

      print("Uploading tracking numbers...")
      group_site_manager = GroupSiteManager(config, driver_creator)
      try:
        group_site_manager.upload(new_trackings)
      except:
        send_error_email(email_sender, "Error uploading tracking numbers")
        raise

      print("Adding results to Google Sheets")
      tracking_uploader = TrackingUploader(config)
      try:
        tracking_uploader.upload_trackings(new_trackings)
      except:
        send_error_email(email_sender, "Error uploading to Google Sheets")
        raise

    print("Writing results to file")
    try:
      tracking_output.save_trackings(new_trackings)
    except:
      send_error_email(email_sender, "Error writing output file")
      raise
    print("Done")
  except:
    print("Exception thrown after looking at the emails.")
    if not args.seen:
      print("Marking all relevant emails as unread to reset.")
    amazon_tracking_retriever.back_out_of_all()
    bestbuy_tracking_retriever.back_out_of_all()
    if not args.seen:
      print("Marked all as unread.")
    raise


if __name__ == "__main__":
  main()
