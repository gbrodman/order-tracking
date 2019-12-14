#!/usr/bin/env python3

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
  args, _ = parser.parse_known_args()

  driver_creator = DriverCreator()

  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)
  email_config = config['email']
  email_sender = EmailSender(email_config)

  print("Retrieving Amazon tracking numbers from email...")
  amazon_tracking_retriever = AmazonTrackingRetriever(config, args, driver_creator)
  try:
    trackings = amazon_tracking_retriever.get_trackings()
  except:
    send_error_email(email_sender, "Error retrieving Amazon emails")
    raise

  if amazon_tracking_retriever.failed_email_ids:
    print(
        "Found %d Amazon emails without buying group labels and marked them as unread. Continuing..."
        % len(amazon_tracking_retriever.failed_email_ids))

  print("Retrieving Best Buy tracking numbers from email...")
  bestbuy_tracking_retriever = BestBuyTrackingRetriever(config, args, driver_creator)
  try:
    bb_trackings = bestbuy_tracking_retriever.get_trackings()
    trackings.extend(bb_trackings)
  except:
    send_error_email(email_sender, "Error retrieving BB emails")
    raise

  if bestbuy_tracking_retriever.failed_email_ids:
    print(
        "Found %d BB emails without buying group labels and marked them as unread. Continuing..."
        % len(bestbuy_tracking_retriever.failed_email_ids))

  try:
    print("Found %d total tracking numbers" % len(trackings))

    # We only need to process and upload new tracking numbers if there are any;
    # otherwise skip straight to processing existing locally stored data.
    if trackings:
      email_sender.send_email(trackings)

      print("Uploading tracking numbers...")
      group_site_manager = GroupSiteManager(config, driver_creator)
      try:
        group_site_manager.upload(trackings)
      except:
        send_error_email(email_sender, "Error uploading tracking numbers")
        raise

      print("Adding results to Google Sheets")
      tracking_uploader = TrackingUploader(config)
      try:
        tracking_uploader.upload_trackings(trackings)
      except:
        send_error_email(email_sender, "Error uploading to Google Sheets")
        raise

    print("Writing results to file")
    tracking_output = TrackingOutput(config)
    try:
      tracking_output.save_trackings(trackings)
    except:
      send_error_email(email_sender, "Error writing output file")
      raise
    print("Done")
  except:
    print(
        "Exception thrown after looking at the emails. Marking all relevant emails as unread to reset."
    )
    amazon_tracking_retriever.back_out_of_all()
    bestbuy_tracking_retriever.back_out_of_all()
    print("Marked all as unread")
    raise


if __name__ == "__main__":
  main()
