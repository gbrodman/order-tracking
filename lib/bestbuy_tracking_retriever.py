import re
from lib.email_tracking_retriever import EmailTrackingRetriever


class BestBuyTrackingRetriever(EmailTrackingRetriever):

  tracking_regex = r'Tracking #[<>br \/]*<a href="[^>]*>([A-Za-z0-9.]+)<\/a>'
  order_id_regex = r'(BBY01-\d{12})'

  def get_order_ids_from_email(self, raw_email):
    result = set()
    result.add(self._get_order_id(raw_email))
    return result

  def get_price_from_email(self, raw_email):
    return None  # not implementable

  def get_tracking_number_from_email(self, raw_email):
    match = re.search(self.tracking_regex, raw_email)
    if not match:
      return None
    return match.group(1)

  def get_from_email_address(self):
    return "BestBuyInfo@emailinfo.bestbuy.com"

  def get_merchant(self) -> str:
    return "Best Buy"

  def get_order_url_from_email(self, raw_email):
    order_id = self._get_order_id(raw_email)
    return "https://www.bestbuy.com/profile/ss/orders/order-details/%s/view" % order_id

  def _get_order_id(self, raw_email):
    match = re.search(self.order_id_regex, raw_email)
    if not match:
      return None
    return match.group(1)

  def get_items_from_email(self, data):
    return ""
