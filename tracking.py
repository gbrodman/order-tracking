import re


def from_row(row):
  if len(row) >= 5:
    url = row[4]
  else:
    url = None
  if len(row) >= 6:
    ship_date = row[5]
  else:
    ship_date = '0'
  if len(row) >= 7:
    group = row[6]
  else:
    group = ''
  if len(row) >= 8:
    tracked_cost = float(row[7].replace(',', '').replace('$', ''))
  else:
    tracked_cost = 0.0
  if len(row) >= 9:
    items = row[8]
  else:
    items = ''
  return Tracking(row[0], group, row[1].split(","), row[2], row[3], url,
                  ship_date, tracked_cost, items)


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
