import imaplib
import os
import pickle
import quopri
import re

from bs4 import BeautifulSoup
from lib.objects_to_drive import ObjectsToDrive
from tqdm import tqdm
from typing import Any, Dict, List, Set

OUTPUT_FOLDER = "output"
CANCELLATIONS_FILENAME = "cancellations.pickle"
CANCELLATIONS_FILE = OUTPUT_FOLDER + "/" + CANCELLATIONS_FILENAME


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
    for email_id in tqdm(
        all_email_ids, desc="Fetching cancellations", unit="email"):
      if email_id not in self.email_id_dict:
        self.email_id_dict[email_id] = self.get_cancellations_from_email(
            mail, email_id)
        self.flush()

      order_to_cancelled_items = self.email_id_dict[email_id]
      for order_id in order_to_cancelled_items:
        if order_id not in result:
          result[order_id] = []
        result[order_id].extend(order_to_cancelled_items[order_id])

    return result

  def get_all_email_ids(self, mail) -> Set[str]:
    subject_searches = [[
        "Successful cancellation of", "from your Amazon.com order"
    ], ["Partial item(s) cancellation from your Amazon.com order"]]
    result_ids = set()
    for search_terms in subject_searches:
      search_terms = ['(SUBJECT "%s")' % phrase for phrase in search_terms]
      status, response = mail.uid('SEARCH', None, *search_terms)
      email_ids = response[0].decode('utf-8')
      result_ids.update(email_ids.split())
    return result_ids

  def get_cancellations_from_email(self, mail,
                                   email_id) -> Dict[str, List[str]]:
    result, data = mail.uid("FETCH", email_id, "(RFC822)")
    raw_email = data[0][1]
    order = re.findall("Order #[ ]?(\d{3}-\d{7}-\d{7})", str(raw_email))[0]

    cancelled_items = []
    soup = BeautifulSoup(
        quopri.decodestring(raw_email),
        features="html.parser",
        from_encoding="iso-8859-1")

    cancelled_header = soup.find('h3', text="Canceled Items")
    parent = cancelled_header.parent.parent.parent
    cancelled_items = [t.text.strip() for t in parent.find_all('li')]
    return {order: cancelled_items}

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
