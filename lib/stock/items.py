class Item:

  def __init__(self, asin, desc, price):
    self.asin = asin
    self.desc = desc
    self.price = price

  def to_row(self) -> list:
    return [self.asin, self.desc, self.price]

  def get_header(self) -> list:
    return ["ASIN", "Item Desc", "Price"]


def from_row(header, row) -> Item:
  asin = row[header.index("ASIN")]
  desc = row[header.index("Item Desc")]
  price_str = str(row[header.index("Price")])
  price = float(price_str) if price_str else None
  return Item(asin, desc, price)
