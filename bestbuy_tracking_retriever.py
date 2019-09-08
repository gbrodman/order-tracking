import re
from email_tracking_retriever import EmailTrackingRetriever


class BestBuyTrackingRetriever(EmailTrackingRetriever):

  tracking_regex = r'Tracking #[<>br \/]*<a href="[^>]*>([A-Za-z0-9.]+)<\/a>'
  order_id_regex = r'(BBY01-\d{12})'

  def get_order_ids_from_email(self, raw_email):
    return set([re.search(self.order_id_regex, raw_email).group(1)])

  def get_price_from_email(self, raw_email):
    return None  # not implementable

  def get_tracking_number_from_email(self, raw_email):
    return re.search(self.tracking_regex, raw_email).group(1)

  def get_from_email_address(self):
    return "BestBuyInfo@emailinfo.bestbuy.com"

  def get_order_url_from_email(self, raw_email):
    order_id = list(self.get_order_ids_from_email(raw_email))[0]
    return "https://www.bestbuy.com/profile/ss/orders/order-details/%s/view" % order_id
