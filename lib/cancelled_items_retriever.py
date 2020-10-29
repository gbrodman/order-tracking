import email
import quopri
import re
import sys
import traceback
import lib.email_auth as email_auth
from tenacity import retry, stop_after_attempt, wait_exponential

from bs4 import BeautifulSoup
from enum import Enum

from lib.debounce import debounce
from lib.object_retriever import ObjectRetriever
from tqdm import tqdm
from typing import Dict, List, Tuple

CANCELLATIONS_FILENAME = "cancellations.pickle"


class CancFmt(Enum):
  VOLUNTARY = 1
  INVOLUNTARY = 2
  IRRELEVANT = 3


class CancQty(Enum):
  YES = 1
  NO = 2


class CancelledItemsRetriever:

  def __init__(self, config):
    self.retriever = ObjectRetriever(config)
    # map of {email_id: {order_id: cancelled_items}}
    self.email_id_dict = self.retriever.load(CANCELLATIONS_FILENAME)

  # returns map of order_id ->
  def get_cancelled_items(self) -> Dict[str, List[str]]:
    mail = self.load_mail()
    all_email_ids = self.get_all_email_ids(mail)

    result = {}
    for email_id, canc_info in tqdm(
        all_email_ids.items(), desc="Fetching cancellations", unit="email"):
      if email_id not in self.email_id_dict:
        email_result = self.get_cancellations_from_email(mail, email_id, canc_info)
        if email_result:
          self.email_id_dict[email_id] = email_result
          self.flush()
        else:
          continue

      order_to_cancelled_items = self.email_id_dict[email_id]
      for order_id in order_to_cancelled_items:
        if order_id not in result:
          result[order_id] = []
        result[order_id].extend(order_to_cancelled_items[order_id])

    return result

  @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=120))
  def get_all_email_ids(self, mail) -> Dict[str, Tuple[CancFmt, CancQty]]:
    subject_searches = {
        ('Your Amazon.com order', 'has been canceled'): (CancFmt.IRRELEVANT, CancQty.NO),
        ('Your Amazon.com Order', 'Has Been Canceled'): (CancFmt.IRRELEVANT, CancQty.NO),
        ('Your Amazon.com Order', 'Has Been Cancelled'): (CancFmt.IRRELEVANT, CancQty.NO),
        ('Your AmazonSmile order', 'has been canceled'): (CancFmt.IRRELEVANT, CancQty.NO),
        ('Your AmazonSmile order', 'has been cancelled'): (CancFmt.IRRELEVANT, CancQty.NO),
        ('Item canceled for your Amazon.com order',): (CancFmt.IRRELEVANT, CancQty.NO),
        (
            "Successful cancellation of",
            "from your AmazonSmile order",
        ): (CancFmt.VOLUNTARY, CancQty.YES),
        (
            "Successful cancellation of",
            "from your Amazon.com order",
        ): (CancFmt.VOLUNTARY, CancQty.YES),
        ("Partial item(s) cancellation from your Amazon.com order",):
            (CancFmt.VOLUNTARY, CancQty.NO),
        ("item has been canceled from your AmazonSmile order",): (CancFmt.INVOLUNTARY, CancQty.NO),
        ("items have been canceled from your AmazonSmile order",):
            (CancFmt.INVOLUNTARY, CancQty.NO),
        ("items have been canceled from your Amazon.com order",): (CancFmt.INVOLUNTARY, CancQty.NO),
        ("item has been canceled from your Amazon.com order",): (CancFmt.INVOLUNTARY, CancQty.NO)
    }
    result_ids = dict()
    for search_terms, canc_info in subject_searches.items():
      search_terms = [f'(SUBJECT "{phrase}")' for phrase in search_terms]
      status, response = mail.uid('SEARCH', None, *search_terms)
      email_ids = response[0].decode('utf-8')
      for email_id in email_ids.split():
        result_ids[email_id] = canc_info
    return result_ids

  @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=120))
  def get_cancellations_from_email(self, mail, email_id: str,
                                   canc_info: Tuple[CancFmt, CancQty]) -> Dict[str, List[str]]:
    try:
      result, data = mail.uid("FETCH", email_id, "(RFC822)")
    except Exception as e:
      raise Exception(f"Error retrieving email UID {email_id}") from e
    try:
      raw_email = data[0][1]
      orders = re.findall("(\d{3}-\d{7}-\d{7})", str(raw_email))
      if not orders:
        return {}
      order = orders[0]

      cancelled_items = []
      soup = BeautifulSoup(
          quopri.decodestring(raw_email), features="html.parser", from_encoding="iso-8859-1")

      if canc_info[0] == CancFmt.VOLUNTARY:
        cancelled_header = soup.find("h3", text="Canceled Items")
      elif canc_info[0] == CancFmt.INVOLUNTARY:
        cancelled_header = soup.find("span", text="Canceled Items")
      elif canc_info[0] == CancFmt.IRRELEVANT:
        return {order: []}
      else:
        raise Exception(f"Can't handle cancellation format {canc_info[0]}")
      parent = cancelled_header.parent.parent.parent
      cancelled_items = []
      for li in parent.find_all('li'):
        # Each li contains a single link whose link text is the item name.
        canc_item = li.find('a').text.strip()
        # If cancellation email format contains quantity info, then use the string from
        # Amazon as-is, otherwise prepend with "??" to indicate indeterminate quantity.
        cancelled_items.append(canc_item if canc_info[1] == CancQty.YES else f"?? {canc_item}")
      return {order: cancelled_items}
    except Exception as e:
      msg = email.message_from_string(str(data[0][1], 'utf-8'))
      print(
          f"Received exception with message '{str(e)}' when processing cancellation email with subject {msg['Subject']}:"
      )
      traceback.print_exc(file=sys.stdout)
      print("Continuing...")
      return None

  @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=120))
  def load_mail(self):
    mail = email_auth.email_authentication()
    mail.select('"[Gmail]/All Mail"')
    return mail

  @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=120))
  @debounce(2)
  def flush(self) -> None:
    self.retriever.flush(self.email_id_dict, CANCELLATIONS_FILENAME)
