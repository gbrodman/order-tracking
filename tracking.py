import re


def from_row(header, row):
  tracking = row[header.index('Tracking Number')]
  orders = set(row[header.index('Order Number(s)')].split(
      ',')) if 'Order Number(s)' in header else set()
  price_str = row[header.index('Price')].replace(',', '').replace(
      '$', '') if 'Price' in header else ''
  price = float(price_str) if price_str else 0.0
  to_email = row[header.index("To Email")]
  url = row[header.index("Order URL")]
  ship_date = row[header.index("Ship Date")]
  group = row[header.index("Group")]
  tracked_cost = float(row[header.index('Amount Reimbursed')].replace(
      ',', '').replace('$', '')) if 'Amount Reimbursed' in header else 0.0
  items = row[header.index("Items")] if items in header else ""
  return Tracking(tracking, group, orders, price, to_email, url, ship_date,
                  tracked_cost, items)


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
               items=''):
    self.tracking_number = tracking_number
    self.group = group
    self.order_ids = order_ids
    self.price = price
    self.to_email = to_email
    self.url = url
    self.ship_date = ship_date
    self.tracked_cost = tracked_cost
    self.items = items

  def __setstate__(self, state):
    self.__init__(**state)

  def __str__(self):
    return "number: %s, group: %s, order(s): %s, price: %s, to_email: %s, url: %s, ship_date: %s" % (
        self.tracking_number, self.group, self.order_ids, self.price,
        self.to_email, self.url, self.ship_date)

  def to_row(self):
    hyperlink = self._create_hyperlink()
    return [
        hyperlink, ", ".join(self.order_ids), self.price, self.to_email,
        self.url, self.ship_date, self.group, self.tracked_cost, self.items
    ]

  def get_header(self):
    return [
        "Tracking Number", "Order Number(s)", "Price", "To Email", "Order URL",
        "Ship Date", "Group", "Amount Reimbursed", "Items"
    ]

  def _create_hyperlink(self):
    link = self._get_tracking_url()
    if link == None:
      return self.tracking_number
    return '=HYPERLINK("%s", "%s")' % (link, self.tracking_number)

  def _get_tracking_url(self):
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
