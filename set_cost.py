#!/usr/bin/env python3

import yaml
from lib.order_info import OrderInfo, OrderInfoRetriever

CONFIG_FILE = "config.yml"


def main():
  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)

  order_info_retriever = OrderInfoRetriever(config)
  while True:
    order = input("Enter order ID: ").strip()
    if not order:
      break
    cost = float(input("Enter cost: ").strip())
    # We don't (yet?) support manual entry of the email_id because it's a little
    # bit of hassle to find through the Web UI. Reuse the email ID if there is one
    existing_order_info = order_info_retriever.get_order_info(order)
    email_id = existing_order_info.email_id if existing_order_info else None
    order_info_retriever.orders_dict[order] = OrderInfo(email_id, cost)
    order_info_retriever.flush()


if __name__ == "__main__":
  main()
