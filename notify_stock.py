from lib.stock import items
from lib.stock import emails
from lib.stock.item_price_retriever import ItemPriceRetriever
from lib.email_sender import EmailSender
from lib.objects_to_sheet import ObjectsToSheet
import yaml

CONFIG_FILE = "config.yml"


def create_email_content(new_items):
  content = "We found the following newly in-stock items (or reduced prices):\n\n"
  for item in new_items:
    content += f"ASIN: {item.asin}, Description: {item.desc}, Price: {item.price}"
    content += "\n"
  return content


if __name__ == "__main__":
  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)

  sheet_id = config['stockNotificationSheetId']
  retriever = ItemPriceRetriever()
  objects_to_sheet = ObjectsToSheet()

  item_list = objects_to_sheet.download_from_sheet(items.from_row, sheet_id,
                                                   "Items")

  prices_map = retriever.get_prices([item.asin for item in item_list])
  new_items = []
  for item in item_list:
    new_price = prices_map[item.asin]
    prev_price = item.price
    item.price = new_price
    if new_price and (not prev_price or new_price < prev_price):
      new_items.append(item)

  objects_to_sheet.upload_to_sheet(item_list, sheet_id, "Items")

  email_list = objects_to_sheet.download_from_sheet(emails.from_row, sheet_id,
                                                    "Emails")
  email_sender = EmailSender(config['email'])

  if new_items:
    content = create_email_content(new_items)
    for email_obj in email_list:
      to = email_obj.email_address
      email_sender.send_email_content("Newly in-stock Amazon items", content,
                                      to)
