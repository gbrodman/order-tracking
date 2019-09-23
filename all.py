#!/usr/bin/env python3

import sys
import get_tracking_numbers
import reconcile


def main(argv):
  get_tracking_numbers.main(argv)
  reconcile.main(argv)


if __name__ == "__main__":
  main(sys.argv)
