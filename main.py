#!/usr/bin/env python3

import sys
import get_tracking_numbers
import import_report
import manual_input
import reconcile


def get_choice():
  while True:
    print("Buying Group Reconciliation Tool")
    print("Choose an option, or 0 to exit: ")
    print("1: Get tracking numbers and upload to BG portals and Google Sheets")
    print("2: Reconcile shipments with results from BG portals")
    print("3: Manually import or delete tracking numbers and order details")
    print("4: Import an Amazon Business spreadsheet from a Google Sheet")
    print("")
    value = input("Enter your choice [1-4] or 0 to exit: ")
    try:
      int_value = int(value)
      if int_value < 0 or int_value > 4:
        raise Exception
      return int_value
    except:
      print("Please enter an integer 1-4 or 0 to exit.")


def main(argv):
  choice = get_choice()
  if choice == 0:
    quit()
  elif choice == 1:
    get_tracking_numbers.main(argv)
  elif choice == 2:
    reconcile.main(argv)
  elif choice == 3:
    manual_input.main(argv)
  elif choice == 4:
    import_report.main(argv)


if __name__ == "__main__":
  main(sys.argv)
