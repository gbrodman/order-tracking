import email
import imaplib
import os
import pickle
import quopri
import re
import sys
import traceback

from bs4 import BeautifulSoup
from enum import Enum
from lib.objects_to_drive import ObjectsToDrive
from tqdm import tqdm
from typing import Any, Dict, List, Set, Tuple

OUTPUT_FOLDER = "output"
CANCELLATIONS_FILENAME = "cancellations.pickle"
CANCELLATIONS_FILE = OUTPUT_FOLDER + "/" + CANCELLATIONS_FILENAME


class CancFmt(Enum):
  VOLUNTARY = 1
  INVOLUNTARY = 2


class CancQty(Enum):
  YES = 1
  NO = 2


class CancelledItemsRetriever:

  def __init__(self, config):
    self.config = config
    # map of {email_id: {order_id: cancelled_items}}
    self.email_id_dict = self.load_dict()

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

  def get_all_email_ids(self, mail) -> Dict[str, Tuple[CancFmt, CancQty]]:
    subject_searches = {
        ("Successful cancellation of", "from your Amazon.com order",): (CancFmt.VOLUNTARY, CancQty.YES),
        ("Partial item(s) cancellation from your Amazon.com order",): (CancFmt.VOLUNTARY, CancQty.NO),
        ("item has been canceled from your AmazonSmile order",): (CancFmt.INVOLUNTARY, CancQty.NO),
        ("items have been canceled from your AmazonSmile order",): (CancFmt.INVOLUNTARY, CancQty.NO),
        ("items have been canceled from your Amazon.com order",): (CancFmt.INVOLUNTARY, CancQty.NO),
        ("item has been canceled from your Amazon.com order",): (CancFmt.INVOLUNTARY, CancQty.NO)}
    result_ids = dict()
    for search_terms, canc_info in subject_searches.items():
      search_terms = [f'(SUBJECT "{phrase}")' for phrase in search_terms]
      status, response = mail.uid('SEARCH', None, *search_terms)
      email_ids = response[0].decode('utf-8')
      for email_id in email_ids.split():
        result_ids[email_id] = canc_info
    return result_ids

  def get_cancellations_from_email(self, mail, email_id: str,
                                   canc_info: Tuple[CancFmt, CancQty]) -> Dict[str, List[str]]:
    try:
      result, data = mail.uid("FETCH", email_id, "(RFC822)")
    except Exception as e:
      raise Exception(f"Error retrieving email UID {email_id}") from e
    try:
      raw_email = data[0][1]
      order = re.findall("(\d{3}-\d{7}-\d{7})", str(raw_email))[0]

      cancelled_items = []
      soup = BeautifulSoup(
          quopri.decodestring(raw_email),
          features="html.parser",
          from_encoding="iso-8859-1")

      if canc_info[0] == CancFmt.VOLUNTARY:
        cancelled_header = soup.find("h3", text="Canceled Items")
      elif canc_info[0] == CancFmt.INVOLUNTARY:
        cancelled_header = soup.find("span", text="Canceled Items")
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

  def load_mail(self):
    mail = imaplib.IMAP4_SSL(self.config['email']['imapUrl'])
    mail.login(self.config['email']['username'],
               self.config['email']['password'])
    mail.select('"[Gmail]/All Mail"')
    return mail

  def flush(self) -> None:
    if not os.path.exists(OUTPUT_FOLDER):
      os.mkdir(OUTPUT_FOLDER)

    with open(CANCELLATIONS_FILE, 'wb') as stream:
      pickle.dump(self.email_id_dict, stream)

    objects_to_drive = ObjectsToDrive()
    objects_to_drive.save(self.config, CANCELLATIONS_FILENAME,
                          CANCELLATIONS_FILE)

  def load_dict(self) -> Any:
    objects_to_drive = ObjectsToDrive()
    from_drive = objects_to_drive.load(self.config, CANCELLATIONS_FILENAME)
    if from_drive:
      return from_drive

    if not os.path.exists(CANCELLATIONS_FILE):
      return {}

    with open(CANCELLATIONS_FILE, 'rb') as stream:
      return pickle.load(stream)
