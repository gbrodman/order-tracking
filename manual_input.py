#!/usr/bin/env python3

import yaml
from lib.expected_costs import ExpectedCosts
from lib.tracking import Tracking
from lib.tracking_output import TrackingOutput

CONFIG_FILE = "config.yml"


def get_required_from_options(prompt, options):
  while True:
    result = get_required(prompt + " [" + "/".join(options) + "]: ")
    if result.lower()[0] in options:
      return result.lower()[0]


def get_optional(prompt):
  return input(prompt).strip()


def get_required(prompt):
  result = ""
  while not result:
    result = str(input(prompt)).strip()
  return result


def get_orders_to_costs():
  result = {}
  while True:
    order_id = get_optional("Enter order #, or blank if no ordrers are left: ")
    if not order_id:
      break
    price = float(get_required("Enter order cost, e.g. 206.76: "))
    result[order_id] = price
  return result


def run_delete(config):
  print("Manual deletion of Tracking object")
  tracking_number = get_required("Tracking number: ")
  tracking_output = TrackingOutput()
  existing_trackings = tracking_output.get_existing_trackings(config)

  found_list = [
      tracking for tracking in existing_trackings
      if tracking.tracking_number == tracking_number
  ]
  if found_list:
    to_delete = found_list[0]
    print("This is the Tracking object: %s" % to_delete)
    submit = get_required_from_options(
        "Are you sure you want to delete this tracking?", ['y', 'n'])
    if submit == 'y':
      existing_trackings.remove(to_delete)
      tracking_output._write_merged(config, existing_trackings)
    else:
      print("Deletion stopped.")
  else:
    print("Could not find that tracking number.")


def run_add(config):
  print("Manual input of Tracking object.")
  tracking_number = get_required("Tracking number: ")
  orders_to_costs = get_orders_to_costs()
  ship_date = get_required("Ship date, formatted YYYY-MM-DD, e.g. 2019-01-31: ")
  group = get_required("Group, e.g. mysbuyinggroup: ")
  email = get_optional("Email address (can leave blank): ")
  order_url = get_optional("Order url (can leave blank): ")
  merchant = get_optional("Merchant (can leave blank): ")
  description = get_optional("Item descriptions (can leave blank): ")
  tracking = Tracking(tracking_number, group, set(orders_to_costs.keys()), '',
                      email, order_url, ship_date, 0.0, description, merchant)
  print("Resulting tracking object: ")
  print(tracking)
  print("Order to cost map: ")
  print(orders_to_costs)
  submit = get_required_from_options("Submit? ", ['y', 'n'])
  if submit == 'y':
    output = TrackingOutput()
    output.save_trackings(config, [tracking])
    print("Wrote tracking")
    ec = ExpectedCosts(config)
    ec.costs_dict.update(orders_to_costs)
    ec.flush()
    print("Wrote billed amounts")
    print("Run get_order_tracking.py to combine this with existing trackings")
  else:
    print("Submission cancelled.")


def main(argv):
  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)
  action = get_required_from_options(
      "Enter 'n' for new tracking, 'd' to delete existing", ["n", "d"])
  if action == "n":
    run_add(config)
  elif action == "d":
    run_delete(config)


if __name__ == "__main__":
  main([])
