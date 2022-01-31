import re
from typing import Tuple, Optional, List

from lib.email_tracking_retriever import EmailTrackingRetriever


class WalmartTrackingRetriever(EmailTrackingRetriever):

  tracking_regexes = [
      r'<a\s*href="(.*)\s*(.*)\s*<span class="columnHeader.*\s*(.*)<\/a>'
  ]
  order_id_regex = r'(\d{7}-\d{6})'

  def get_order_ids_from_email(self, raw_email):
    result = set()
    result.add(self._get_order_id(raw_email))
    return result

  def get_price_from_email(self, raw_email):
    return None  # not implementable

  def get_tracking_numbers_from_email(self, raw_email, from_email: str,
                                      to_email: str) -> List[Tuple[str, Optional[str]]]:
    for regex in self.tracking_regexes:
      match = re.search(regex, raw_email)
      if match:
        # The second part of the tuple here is the shipping status, which would need
        # to be retrieved from a shipping status web page (like it is for Amazon).
        return [(match.group(1), None)]
    return []

  def get_subject_searches(self):
    return [["Some items have shipped:"], ["Shipped:"], ["Shipped and arriving"]]

  def get_merchant(self) -> str:
    return "Walmart"

  def _get_order_id(self, raw_email):
    match = re.search(self.order_id_regex, raw_email)
    if not match:
      return None
    return match.group(1)

  def get_items_from_email(self, email_str):
    return ""

  def get_delivery_date_from_email(self, data):
    return ""
