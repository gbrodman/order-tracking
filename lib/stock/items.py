from .. import create_url


class Item:

  def __init__(self, asin, desc, price, notify_if_below):
    self.asin = asin
    self.desc = desc
    self.price = price
    self.notify_if_below = notify_if_below

  def to_row(self) -> list:
    return [
        self.asin, self.desc, self.price, self.notify_if_below,
        create_url.create_url([self.asin])
    ]

  def get_header(self) -> list:
    return ["ASIN", "Item Desc", "Price", "Notify If Below", "URL"]


def from_row(header, row) -> Item:
  asin = row[header.index("ASIN")]
  desc = row[header.index("Item Desc")]
  price_str = str(row[header.index("Price")])
  price = float(price_str) if price_str else None
  notify_if_below_str = str(row[header.index(
      "Notify If Below")]) if "Notify If Below" in header else None
  notify_if_below = float(notify_if_below_str) if notify_if_below_str else None
  return Item(asin, desc, price, notify_if_below)
