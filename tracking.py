class Tracking:
    def __init__(self, tracking_number, group, order_number, price, to_email):
        self.tracking_number = tracking_number
        self.group = group
        self.order_number = order_number
        self.price = price
        self.to_email = to_email

    def __str__(self):
        return "number: %s, group: %s, order: %s, price: %s, to_email: %s" % (
            self.tracking_number, self.group, self.order_number, self.price,
            self.to_email)
