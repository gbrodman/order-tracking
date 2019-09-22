import re
from typing import Any, List


class Tracking:

  def __init__(self,
               tracking_number,
               group,
               order_ids,
               price,
               to_email,
               url,
               ship_date='0',
               tracked_cost=0.0,
               items='',
               merchant='') -> None:
    self.tracking_number = tracking_number
    self.group = group
    self.order_ids = order_ids
    self.price = price
    self.to_email = to_email
    self.url = url
    self.ship_date = ship_date
    self.tracked_cost = tracked_cost
    self.items = items
    self.merchant = merchant

  def __setstate__(self, state) -> None:
    self.__init__(**state)

  def __str__(self) -> str:
    return "number: %s, group: %s, order(s): %s, price: %s, to_email: %s, url: %s, ship_date: %s, items: %s, merchant: %s" % (
        self.tracking_number, self.group, self.order_ids, self.price,
        self.to_email, self.url, self.ship_date, self.items, self.merchant)

  def to_row(self) -> list:
    hyperlink = self._create_hyperlink()
    return [
        hyperlink, ", ".join(self.order_ids), self.to_email, self.url,
        self.ship_date, self.group, self.tracked_cost, self.merchant, self.items
    ]

  def get_header(self) -> List[str]:
    return [
        "Tracking Number", "Order Number(s)", "To Email", "Order URL",
        "Ship Date", "Group", "Amount Reimbursed", "Merchant", "Items"
    ]

  def _create_hyperlink(self) -> Any:
    link = self._get_tracking_url()
    if link == None:
      return self.tracking_number
    return '=HYPERLINK("%s", "%s")' % (link, self.tracking_number)

  def _get_tracking_url(self) -> Any:
    if self.tracking_number.startswith("TBA"):  # Amazon
      return self.url
    elif self.tracking_number.startswith("1Z"):  # UPS
      return "https://www.ups.com/track?loc=en_US&tracknum=%s" % self.tracking_number
    elif len(self.tracking_number) == 12 or len(
        self.tracking_number) == 15:  # FedEx
      return "https://www.fedex.com/apps/fedextrack/?tracknumbers=%s" % self.tracking_number
    elif len(self.tracking_number) == 22:  # USPS
      return "https://tools.usps.com/go/TrackConfirmAction?qtc_tLabels1=%s" % self.tracking_number
    else:
      print("Unknown tracking number type: %s" % self.tracking_number)
      return None


def from_row(header, row) -> Tracking:
  tracking = row[header.index('Tracking Number')]
  orders = set(row[header.index('Order Number(s)')].split(','))
  price_str = str(row[header.index('Price')]).replace(',', '').replace(
      '$', '') if 'Price' in header else ''
  price = float(price_str) if price_str else 0.0
  to_email = row[header.index("To Email")]
  url = row[header.index("Order URL")]
  ship_date = row[header.index("Ship Date")]
  group = row[header.index("Group")]
  tracked_cost_str = row[header.index(
      "Amount Reimbursed")] if "Amount Reimbursed" in header else ""
  tracked_cost = float(tracked_cost_str) if tracked_cost_str else 0.0
  items = row[header.index("Items")] if 'Items' in header else ""
  merchant = row[header.index("Merchant")] if 'Merchant' in header else ""
  return Tracking(tracking, group, orders, price, to_email, url, ship_date,
                  tracked_cost, items)
