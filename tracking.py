class Tracking:

    def __init__(self, tracking_number, group, order_number, price):
        self.tracking_number = tracking_number
        self.group = group
        self.order_number = order_number
        self.price = price

    def __str__(self):
        return "number: %s, group: %s, order: %s, price: %s" % (self.tracking_number, self.group, self.order_number, self.price)
