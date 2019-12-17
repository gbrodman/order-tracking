#!/usr/bin/env python3

import generate_url
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
    print("5: Generate an Amazon cart URL")
    print("")
    value = input("Enter your choice [1-5] or 0 to exit: ")
    try:
      int_value = int(value)
      if int_value < 0 or int_value > 5:
        raise Exception
      return int_value
    except:
      print("Please enter an integer 1-5 or 0 to exit.")


def main():
  choice = get_choice()
  if choice == 0:
    quit()
  elif choice == 1:
    get_tracking_numbers.main()
  elif choice == 2:
    reconcile.main()
  elif choice == 3:
    manual_input.main()
  elif choice == 4:
    import_report.main()
  elif choice == 5:
    generate_url.main()


if __name__ == "__main__":
  main()
