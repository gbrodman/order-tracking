import re
from typing import Tuple, Optional, List

from lib.email_tracking_retriever import EmailTrackingRetriever


class BestBuyTrackingRetriever(EmailTrackingRetriever):

  tracking_regex = r'Tracking #[<>br \/]*<a href="[^>]*>([A-Za-z0-9.]+)<\/a>'
  order_id_regex = r'(BBY(?:01|TX)-\d{12})'

  def get_order_ids_from_email(self, raw_email):
    result = set()
    result.add(self._get_order_id(raw_email))
    return result

  def get_price_from_email(self, raw_email):
    return None  # not implementable

  def get_tracking_numbers_from_email(self, raw_email,
                                      to_email: str) -> List[Tuple[str, Optional[str]]]:
    match = re.search(self.tracking_regex, raw_email)
    if not match:
      return []
    # The second part of the tuple here is the shipping status, which would need
    # to be retrieved from a shipping status web page (like it is for Amazon).
    return [(match.group(1), None)]

  def get_subject_searches(self):
    return [["Your order #BBY01", "has shipped"], ["Your order #BBYTX", "has shipped"]]

  def get_merchant(self) -> str:
    return "Best Buy"

  def _get_order_id(self, raw_email):
    match = re.search(self.order_id_regex, raw_email)
    if not match:
      return None
    return match.group(1)

  def get_items_from_email(self, data):
    return ""

  def get_delivery_date_from_email(self, data):
    return ""
