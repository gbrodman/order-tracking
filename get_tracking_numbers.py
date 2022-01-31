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

from lib import util
from lib.amazon_tracking_retriever import AmazonTrackingRetriever
from lib.bestbuy_tracking_retriever import BestBuyTrackingRetriever
from lib.walmart_tracking_retriever import WalmartTrackingRetriever
from lib.config import open_config
from lib.driver_creator import DriverCreator
from lib.email_sender import EmailSender
from lib.group_site_manager import GroupSiteManager
from lib.tracking_output import TrackingOutput
from lib.tracking_uploader import TrackingUploader


def send_error_email(email_sender, subject):
  email_sender.send_email_content(subject, util.get_traceback_lines())


def main():
  parser = argparse.ArgumentParser(description='Get tracking #s script')
  parser.add_argument("--seen", action="store_true")
  parser.add_argument("--days")
  args, _ = parser.parse_known_args()

  driver_creator = DriverCreator()

  config = open_config()
  email_config = config['email']
  email_sender = EmailSender(email_config)

  print("Retrieving Amazon tracking numbers from email ...")
  amazon_tracking_retriever = AmazonTrackingRetriever(config, args, driver_creator)
  try:
    trackings = amazon_tracking_retriever.get_trackings()
  except:
    send_error_email(email_sender, "Error retrieving Amazon emails")
    raise

  print("Retrieving Best Buy tracking numbers from email ...")
  bestbuy_tracking_retriever = BestBuyTrackingRetriever(config, args, driver_creator)
  try:
    trackings.update(bestbuy_tracking_retriever.get_trackings())
  except:
    send_error_email(email_sender, "Error retrieving Best Buy emails")
    raise

  print("Retrieving Walmart tracking numbers from email ...")
  walmart_tracking_retriever = WalmartTrackingRetriever(config, args, driver_creator)
  try:
    trackings.update(walmart_tracking_retriever.get_trackings())
  except:
    send_error_email(email_sender, "Error retrieving Walmart emails")
    raise

  try:
    tracking_output = TrackingOutput(config)
    existing_tracking_nos = set(
        [t.tracking_number for t in tracking_output.get_existing_trackings()])
    new_tracking_nos = set(trackings.keys()).difference(existing_tracking_nos)
    print(f"Found {len(new_tracking_nos)} new tracking numbers "
          f"(out of {len(trackings)} total) from emails.")
    new_trackings = [trackings[n] for n in new_tracking_nos]

    # We only need to process new tracking numbers if there are any;
    # otherwise skip straight to processing existing locally stored data.
    if new_trackings:
      try:
        email_sender.send_email(new_trackings)
      except Exception as e:
        # When running --seen, we're often processing a very large number of emails that can
        # take a long time, and the Tracking Numbers email isn't too important to us (but the
        # upload to portals/Sheets definitely is). So don't fail after we've been running for
        # a long time just on account of a failed email.
        if args.seen:
          print(f"Email sending failed with error: {str(e)}\n{util.get_traceback_lines()}")
          print("New trackings are:\n" + "\n".join([str(nt) for nt in new_trackings]))
          print("Continuing to portal/Sheet upload because email sending is non-essential.")
        else:
          raise e

    print("Uploading all tracking numbers...")
    group_site_manager = GroupSiteManager(config, driver_creator)
    try:
      group_site_manager.upload(trackings.values())
    except:
      send_error_email(email_sender, "Error uploading tracking numbers")
      if args.seen:
        print("Error uploading tracking numbers; skipping.")
      else:
        raise

    reconcilable_trackings = [t for t in new_trackings if t.reconcile]

    # Also only add new trackings to the sheet
    print("Adding results to Google Sheets")
    tracking_uploader = TrackingUploader(config)
    try:
      tracking_uploader.upload_trackings(reconcilable_trackings)
    except:
      send_error_email(email_sender, "Error uploading to Google Sheets")
      if args.seen:
        print("Error uploading to Google Sheets; skipping.")
      else:
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
