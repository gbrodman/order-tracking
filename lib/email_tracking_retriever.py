import datetime
import email
import imaplib
import lib.tracking
import lib.email_auth as email_auth
from abc import ABC, abstractmethod
from tqdm import tqdm
from lib.tracking import Tracking
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Any, Callable, Optional, Tuple, TypeVar

_FuncT = TypeVar('_FuncT', bound=Callable)


class EmailTrackingRetriever(ABC):

  def __init__(self, config, args, driver_creator) -> None:
    self.config = config
    self.email_config = config['email']
    self.args = args
    self.driver_creator = driver_creator
    self.failed_email_ids = []
    self.all_email_ids = []

  def back_out_of_all(self) -> None:
    """
    Called when an exception is received. If running in the (default) unseen
    mode, then all processed emails are set to unread again.
    """
    self.mark_emails_as_unread(self.all_email_ids)

  def mark_emails_as_unread(self, email_ids) -> None:
    if not self.args.seen:
      for email_id in email_ids:
        self.mark_as_unread(email_id)

  def mark_as_unread(self, email_id) -> None:
    if not self.args.seen:
      mail = self.get_all_mail_folder()
      mail.uid('STORE', email_id, '-FLAGS', '(\Seen)')

  def get_trackings(self) -> list:
    self.all_email_ids = self.get_email_ids()
    seen_adj = "read" if self.args.seen else "unread"
    print(f"Found {len(self.all_email_ids)} {seen_adj} {self.get_merchant()} "
          "shipping emails in the dates we searched.")
    trackings = {}
    mail = self.get_all_mail_folder()
    failed_email_ids = []
    try:
      for email_id in tqdm(self.all_email_ids, desc="Fetching trackings", unit="email"):
        try:
          tracking = self.get_tracking(email_id, mail)
          if tracking:
            trackings[tracking.tracking_number] = tracking
        except Exception as e:
          failed_email_ids.append(email_id)
          tqdm.write(f"Error fetching tracking from email ID {email_id}: {str(e)}")
    except:
      print("Unexpected error when parsing emails.")
      if not self.args.seen:
        print("Marking emails as unread.")
        self.back_out_of_all()
      raise
    if len(failed_email_ids) > 0:
      print(f"Failed retrieving trackings for the following email IDs: {failed_email_ids}.")
      if not self.args.seen:
        print("Marking these emails as unread.")
        self.mark_emails_as_unread(failed_email_ids)
    return trackings

  def get_buying_group(self, raw_email) -> Tuple[str, bool]:
    raw_email = raw_email.upper()
    for group in self.config['groups'].keys():
      group_conf = self.config['groups'][group]
      # An optional "except" list in the config indicates terms that we wish to avoid for this
      # group. If a term is found that's in this list, we will not include this email as part of
      # the group in question. This is useful when two groups share the same address.
      if any([
          str(except_elem).upper() in raw_email
          for except_elem in group_conf.get('except', [])
      ]):
        continue

      reconcile = bool(
          group_conf['reconcile']) if 'reconcile' in group_conf else True
      group_keys = group_conf['keys']
      if isinstance(group_keys, str):
        group_keys = [group_keys]
      for group_key in group_keys:
        if str(group_key).upper() in raw_email:
          return group, reconcile
    return None, True

  @abstractmethod
  def get_order_ids_from_email(self, raw_email) -> Any:
    pass

  @abstractmethod
  def get_price_from_email(self, raw_email) -> Any:
    pass

  @abstractmethod
  def get_tracking_number_from_email(self,
                                     raw_email) -> Tuple[str, Optional[str]]:
    """
    Returns a Tuple of [tracking number, optional shipping status].
    """
    pass

  @abstractmethod
  def get_subject_searches(self) -> Any:
    pass

  @abstractmethod
  def get_merchant(self) -> str:
    pass

  @abstractmethod
  def get_items_from_email(self, data) -> Any:
    pass

  @abstractmethod
  def get_delivery_date_from_email(self, data) -> Any:
    pass

  def get_date_from_msg(self, data) -> str:
    msg = email.message_from_string(str(data[0][1], 'utf-8'))
    msg_date = msg['Date']
    return datetime.datetime.strptime(
        msg_date, '%a, %d %b %Y %H:%M:%S %z').strftime('%Y-%m-%d')

  def get_to_address(self, data) -> str:
    msg = email.message_from_string(str(data[0][1], 'utf-8'))
    return str(msg['To']).replace('<', '').replace('>', '')

  @retry(
      stop=stop_after_attempt(3),
      wait=wait_exponential(multiplier=1, min=2, max=16),
      reraise=True)
  def get_tracking(self, email_id, mail) -> Tracking:
    result, data = mail.uid("FETCH", email_id, "(RFC822)")
    raw_email = str(data[0][1]).replace("=3D",
                                        "=").replace('=\\r\\n', '').replace(
                                            '\\r\\n', '').replace('&amp;', '&')
    to_email = self.get_to_address(data)
    date = self.get_date_from_msg(data)
    price = self.get_price_from_email(raw_email)
    order_ids = self.get_order_ids_from_email(raw_email)
    group, reconcile = self.get_buying_group(raw_email)
    tracking_number, shipping_status = self.get_tracking_number_from_email(
        raw_email)
    tqdm.write(
        f"Tracking: {tracking_number}, Order(s): {order_ids}, Group: {group}, Status: {shipping_status}"
    )
    if tracking_number == None:
      self.failed_email_ids.append(email_id)
      tqdm.write(
          f"Could not find tracking number from email with order(s) {order_ids}"
      )
      self.mark_as_unread(email_id)
      return None

    items = self.get_items_from_email(data)
    if group == None:
      self.failed_email_ids.append(email_id)
      tqdm.write(
          f"Could not find buying group for email with order(s) {order_ids}")
      self.mark_as_unread(email_id)
      return None

    merchant = self.get_merchant()
    delivery_date = self.get_delivery_date_from_email(data)
    return Tracking(tracking_number, group, order_ids, price, to_email, '',
                    date, 0.0, items, merchant, reconcile, delivery_date)

  def get_all_mail_folder(self) -> imaplib.IMAP4_SSL:
    mail = email_auth.email_authentication()
    mail.select('"[Gmail]/All Mail"')
    return mail

  def get_email_ids(self) -> Any:
    date_to_search = self.get_date_to_search()
    mail = self.get_all_mail_folder()
    subject_searches = self.get_subject_searches()

    result = set()
    seen_filter = '(SEEN)' if self.args.seen else '(UNSEEN)'
    for search_terms in subject_searches:
      search_terms = ['(SUBJECT "%s")' % phrase for phrase in search_terms]
      status, response = mail.uid('SEARCH', None, seen_filter,
                                  f'(SINCE "{date_to_search}")', *search_terms)
      email_ids = response[0].decode('utf-8')
      result.update(email_ids.split())

    return result

  def get_date_to_search(self) -> str:
    if self.args.days:
      lookback_days = int(self.args.days)
    elif "lookbackDays" in self.config:
      lookback_days = int(self.config['lookbackDays'])
    else:
      lookback_days = 45
    date = datetime.date.today() - datetime.timedelta(days=lookback_days)
    string_date = date.strftime("%d-%b-%Y")
    print("Searching for emails since %s" % string_date)
    return string_date
