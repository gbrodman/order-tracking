#!/usr/bin/env python3
#
# This is an interactive script for manually entering order information, e.g.
# because a tracking email link isn't working. Just run it from the command-line
# and it'll walk you through the data input process. The most important
# information to enter is the tracking number, order number(s), and cost.
import argparse
import datetime
from typing import Dict
import yaml
from lib.config import open_config
from lib.order_info import OrderInfo, OrderInfoRetriever
from lib.tracking import Tracking
from lib.tracking_output import TrackingOutput

CONFIG_FILE = "config.yml"
TODAY = datetime.date.today().strftime("%Y-%m-%d")


def get_required_from_options(prompt, options):
  while True:
    result = get_required(prompt + " [" + "/".join(options) + "]: ")
    if result.lower()[0] in options:
      return result.lower()[0]


def get_optional_with_default(prompt, default):
  result = input(prompt).strip()
  if result:
    return result
  return default


def get_optional(prompt):
  return input(prompt).strip()


def get_required(prompt):
  result = ""
  while not result:
    result = str(input(prompt)).strip()
  return result


def input_orders() -> Dict[str, OrderInfo]:
  result = {}
  while True:
    order_id = get_optional("Enter order #, or blank if no orders are left: ")
    if not order_id:
      break
    price = float(get_required("Enter order cost, e.g. 206.76: "))
    # We don't (yet?) support manual entry of the email_id because it's a little
    # bit of hassle to find through the Web UI.
    result[order_id] = OrderInfo(None, price)
  return result


def run_add(config):
  print("Add tracking to existing tracking/order cluster.")
  existing_tracking_num = get_required("Enter a tracking number of the existing cluster: ")
  tracking_output = TrackingOutput(config)
  tracking = tracking_output.get_tracking(existing_tracking_num)
  if not tracking:
    print("Error: Tracking does not exist. Aborting.")
    return
  print("Existing tracking data is:")
  print(tracking)
  new_tracking_num = get_optional("Enter new tracking number (or blank to abort): ")
  if not new_tracking_num:
    print("Aborting.")
    return
  tracking.tracking_number = new_tracking_num
  print("New tracking data is:")
  print(tracking)
  submit = get_required_from_options("Save?", ['y', 'n'])
  if submit:
    tracking_output.save_trackings([tracking])
    print("Saved.")
  else:
    print("Cancelled.")

def run_delete(config):
  print("Manual deletion of Tracking object.")
  tracking_number = get_required("Tracking number: ")
  tracking_output = TrackingOutput(config)
  existing_trackings = tracking_output.get_existing_trackings()

  found_list = [
      tracking for tracking in existing_trackings if tracking.tracking_number == tracking_number
  ]
  if found_list:
    to_delete = found_list[0]
    print("This is the Tracking object: %s" % to_delete)
    submit = get_required_from_options("Are you sure you want to delete this tracking?", ['y', 'n'])
    if submit == 'y':
      existing_trackings.remove(to_delete)
      tracking_output._write_merged(existing_trackings)
    else:
      print("Deletion stopped.")
  else:
    print("Could not find that tracking number.")


def run_new(config):
  print("Manual input of Tracking object.")
  print("Optional fields will display a default in brackets if one exists.")
  print("")
  tracking_output = TrackingOutput(config)
  tracking_number = get_required("Tracking number: ")
  tracking = tracking_output.get_tracking(tracking_number)
  if tracking:
    print("This tracking number already exists:")
    print(tracking)
    print("Adding new order(s) to the existing tracking number.")
  orders_to_costs = input_orders()
  if tracking:
    order_ids_set = set(tracking.order_ids)
    order_ids_set.update(orders_to_costs.keys())
    tracking.order_ids = list(order_ids_set)
    tracking.price = ''  # Zero out price for reconcile to fix later.
  else:
    ship_date = get_optional_with_default("Optional ship date, formatted YYYY-MM-DD [%s]: " % TODAY,
                                          TODAY)
    group = get_required("Group, e.g. mysbuyinggroup: ")
    email = get_optional("Optional email address: ")
    order_url = get_optional("Optional order URL: ")
    merchant = get_optional("Optional merchant: ")
    description = get_optional("Optional item descriptions: ")
    tracking = Tracking(tracking_number, group, set(orders_to_costs.keys()), '', email, order_url,
                        ship_date, 0.0, description, merchant)

  print("Resulting tracking object: ")
  print(tracking)
  print("Order to cost map: ")
  print(orders_to_costs)
  submit = get_required_from_options("Submit? 'y' to submit, 'n' to quit: ", ['y', 'n'])
  if submit == 'y':
    tracking_output.save_trackings([tracking], overwrite=True)
    print("Wrote tracking")
    order_info_retriever = OrderInfoRetriever(config)
    order_info_retriever.orders_dict.update(orders_to_costs)
    order_info_retriever.flush()
    print("Wrote billed amounts")
    print("This will be picked up on next reconciliation run.")
  elif submit == 'n':
    print("Submission cancelled.")


def run_auto(config, args):
  if not args.tracking or not args.order or not args.group:
    raise Exception('Must provide tracking, order, and group if doing auto')

  orders = set()
  orders.add(args.order)
  tracking = Tracking(args.tracking, args.group, orders, '', '', '', TODAY, 0.0, '', '')
  print(tracking)
  tracking_output = TrackingOutput(config)
  tracking_output.save_trackings([tracking], overwrite=True)


def main():
  config = open_config()
  parser = argparse.ArgumentParser(description='Adding a tracking number manually')
  parser.add_argument(
      '-a',
      '--auto',
      action="store_true",
      help='Allows input of fields through the script invocation args')
  parser.add_argument('-t', '--tracking', help='Tracking number in question')
  parser.add_argument('-o', '--order', help='Order number to associate this tracking with')
  parser.add_argument('-g', '--group', help='Buying group for this tracking')
  args, _ = parser.parse_known_args()

  if args.auto:
    run_auto(config, args)
    return

  action = get_required_from_options("Enter 'a' to add a tracking number to an existing cluster, "
                                     "'n' for a new tracking, or 'd' to delete a tracking",
                                     ["a", "n", "d"])
  if action == "a":
    run_add(config)
  elif action == "n":
    run_new(config)
  elif action == "d":
    run_delete(config)


if __name__ == "__main__":
  main()
