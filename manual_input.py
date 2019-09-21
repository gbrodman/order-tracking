import yaml
from expected_costs import ExpectedCosts
from tracking import Tracking
from tracking_output import TrackingOutput

CONFIG_FILE = "config.yml"


def get_submit():
  while True:
    result = get_required("Submit? [y/n]: ")
    if result.lower()[0] == "y":
      return True
    elif result.lower()[0] == "n":
      return False


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


if __name__ == "__main__":
  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)

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
  submit = get_submit()
  if submit:
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
