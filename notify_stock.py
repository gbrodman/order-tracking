import argparse
import time
import yaml

from lib.create_url import create_url
from lib.stock import items
from lib.stock import emails
from lib.stock.item_price_retriever import ItemPriceRetriever
from lib.email_sender import EmailSender
from lib.objects_to_sheet import ObjectsToSheet

CONFIG_FILE = "config.yml"


def create_email_content(new_items, all_items, sheet_id):
  content = "We found the following newly in-stock items (or reduced prices):\n\n"
  for item in new_items:
    content += f"{item.desc}, Price: {item.price}, URL: {create_url([item.asin])}"
    content += "\n"

  new_asins = [item.asin for item in new_items]
  in_stock_asins = [item.asin for item in all_items if item.price]

  content += "\nAll new items:\n"
  content += create_url(new_asins)
  content += "\n\n"

  content += "All in-stock items:\n"
  content += create_url(in_stock_asins)

  content += "\n\nConfiguration Google Sheet:\n"
  content += f"https://docs.google.com/spreadsheets/d/{sheet_id}"
  return content


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description='Notifying when items are in stock')
  parser.add_argument("--run-indefinitely", action="store_true")
  args, _ = parser.parse_known_args()
  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)

  sheet_id = config['stockNotificationSheetId']
  retriever = ItemPriceRetriever()
  objects_to_sheet = ObjectsToSheet()

  while True:
    item_list = objects_to_sheet.download_from_sheet(items.from_row, sheet_id,
                                                     "Items")

    prices_map = retriever.get_prices([item.asin for item in item_list])
    new_items = []
    for item in item_list:
      new_price = prices_map.get(item.asin, None)
      prev_price = item.price
      item.price = new_price
      if new_price and (not prev_price or new_price < prev_price) and (
          not item.notify_if_below or new_price < item.notify_if_below):
        new_items.append(item)

    objects_to_sheet.upload_to_sheet(item_list, sheet_id, "Items")

    email_list = objects_to_sheet.download_from_sheet(emails.from_row, sheet_id,
                                                      "Emails")
    email_sender = EmailSender(config['email'])

    if new_items and email_list:
      content = create_email_content(new_items, item_list, sheet_id)
      recipients = [email_obj.email_address for email_obj in email_list]
      email_sender.send_email_content("🚨 Newly in-stock Amazon items 🚨",
                                      content, recipients)
    if args.run_indefinitely:
      print("Sleeping for five minutes...")
      time.sleep(300)
    else:
      break
