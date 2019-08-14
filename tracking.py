class Tracking:

  def __init__(self, tracking_number, group, order_ids, price, to_email):
    self.tracking_number = tracking_number
    self.group = group
    self.order_ids = order_ids
    self.price = price
    self.to_email = to_email

  def __str__(self):
    return "number: %s, group: %s, order(s): %s, price: %s, to_email: %s" % (
        self.tracking_number, self.group, self.order_ids, self.price,
        self.to_email)
