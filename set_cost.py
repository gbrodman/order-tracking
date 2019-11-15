#!/usr/bin/env python3

import sys
import yaml
from lib.expected_costs import ExpectedCosts

CONFIG_FILE = "config.yml"


def main(argv):
  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)

  ec = ExpectedCosts(config)
  while True:
    order = input("Enter order ID: ").strip()
    if not order:
      break
    cost = float(input("Enter cost: ").strip())
    ec.costs_dict[order] = cost
    ec.flush()


if __name__ == "__main__":
  main(sys.argv)
