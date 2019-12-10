#!/usr/bin/env python3

import yaml
from lib.shipment_info import OrderInfo, ShipmentInfo

CONFIG_FILE = "config.yml"


def main():
  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)

  shipment_info = ShipmentInfo(config)
  while True:
    order = input("Enter order ID: ").strip()
    if not order:
      break
    cost = float(input("Enter cost: ").strip())
    # We don't (yet?) support manual entry of the email_id because it's a little
    # bit of hassle to find through the Web UI.
    shipment_info.shipments_dict[order] = OrderInfo(None, cost)
    shipment_info.flush()


if __name__ == "__main__":
  main()
