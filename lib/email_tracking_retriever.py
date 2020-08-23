import base64
import datetime
import email
import imaplib
import socket
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, Tuple, TypeVar, Dict, List

from tqdm import tqdm

import lib.email_auth as email_auth
from lib import util
from lib.tracking import Tracking

_FuncT = TypeVar('_FuncT', bound=Callable)

BASE_64_FLAG = 'Content-Transfer-Encoding: base64'
TODAY = datetime.date.today().strftime('%Y-%m-%d')


class EmailTrackingRetriever(ABC):

  def __init__(self, config, args, driver_creator) -> None:
    self.config = config
    self.email_config = config['email']
    self.args = args
    self.driver_creator = driver_creator
    self.driver = None
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

  def get_trackings(self) -> Dict[str, Tracking]:
    """
    Gets all shipping emails falling within the configured search parameters,
    i.e. all unread or all read within the past N days, and parses them to find
    tracking numbers.  Returns a dict of tracking number to full tracking info
    for successes, and prints out failures.
    """
    self.all_email_ids = self.get_email_ids()
    seen_adj = "read" if self.args.seen else "unread"
    print(f"Found {len(self.all_email_ids)} {seen_adj} {self.get_merchant()} "
          "shipping emails in the dates we searched.")
    trackings = {}
    mail = self.get_all_mail_folder()
    # Emails that throw Exceptions and can't be parsed at all.
    failed_email_ids = []
    # Incomplete tracking information from emails with handled errors.
    incomplete_trackings = []

    self.driver = self.driver_creator.new()
    try:
      for email_id in tqdm(self.all_email_ids, desc="Fetching trackings", unit="email"):
        try:
          for attempt in range(1, 5):  # Make 4 attempts
            try:
              success, new_trackings = self.get_trackings_from_email(email_id, mail)
            except (ConnectionError, socket.error, imaplib.IMAP4.abort):
              tqdm.write(f"Connection lost; reconnecting (attempt {attempt}).")
              # Re-initializing the IMAP connection and retrying should fix most
              # connection-related errors.
              # See https://stackoverflow.com/questions/7575943/eof-error-in-imaplib
              mail = self.get_all_mail_folder()
              continue
            if success:
              for new_tracking in new_trackings:
                trackings[new_tracking.tracking_number] = new_tracking
            else:
              incomplete_trackings.extend(new_trackings)
              self.mark_as_unread(email_id)
            break
        except Exception as e:
          failed_email_ids.append(email_id)
          tqdm.write(f"Unexpected error fetching tracking from email ID {email_id}: "
                     f"{e.__class__.__name__}: {str(e)}: {util.get_traceback_lines()}")
    except Exception as e:
      if not self.args.seen:
        print("Fatal unexpected error parsing emails; marking all as unread.")
        self.back_out_of_all()
      raise Exception("Fatal unexpected fatal error when parsing emails") from e
    finally:
      self.driver.quit()

    if len(incomplete_trackings) > 0:
      print("Couldn't find full tracking info/matching buying group for some emails.\n"
            "Here's what we got:\n" + "\n".join([str(t) for t in incomplete_trackings]))
      if not self.args.seen:
        print("They were already marked as unread.")

    if len(failed_email_ids) > 0:
      print(f"Errored out while retrieving {len(failed_email_ids)} trackings "
            f"with email IDs: {failed_email_ids}.")
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
      if any(
          [str(except_elem).upper() in raw_email for except_elem in group_conf.get('except', [])]):
        continue

      reconcile = bool(group_conf['reconcile']) if 'reconcile' in group_conf else True
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
  def get_tracking_numbers_from_email(self, raw_email, from_email: str,
                                      to_email: str) -> List[Tuple[str, Optional[str]]]:
    """
    Returns a potentially empty list of (tracking number, optional shipping status) tuples.
    """
    pass

  @abstractmethod
  def get_subject_searches(self) -> Any:
    pass

  @abstractmethod
  def get_merchant(self) -> str:
    pass

  @abstractmethod
  def get_items_from_email(self, email_str) -> Any:
    pass

  @abstractmethod
  def get_delivery_date_from_email(self, email_str) -> Any:
    pass

  def get_trackings_from_email(self, email_id, mail) -> Tuple[bool, List[Tracking]]:
    """
    Returns a Tuple of boolean success status and tracking information for a
    given email id. If success is True then the tracking info is complete and
    should be used, otherwise if False then the tracking info is incomplete
    and is only suitable for use as error output.
    """
    email_str = get_email_content(email_id, mail)

    msg = email.message_from_string(email_str)

    email_str = clean_email_content(email_str)
    to_email = str(msg['To']).replace('<', '').replace('>', '') if msg['To'] else ''
    from_email = str(msg['From']).replace('<', '').replace(
        '>', '') if msg['From'] else ''  # Also has display name.
    date = datetime.datetime.strptime(
        msg['Date'], '%a, %d %b %Y %H:%M:%S %z').strftime('%Y-%m-%d') if msg['Date'] else TODAY
    price = self.get_price_from_email(email_str)
    order_ids = self.get_order_ids_from_email(email_str)
    group, reconcile = self.get_buying_group(email_str)
    tracking_nums = self.get_tracking_numbers_from_email(email_str, from_email, to_email)

    if len(tracking_nums) == 0:
      incomplete_tracking = Tracking(None, group, order_ids, price, to_email, '', date, 0.0)
      tqdm.write(f"Could not find tracking number from email; we got: {incomplete_tracking}")
      return False, [incomplete_tracking]

    # TODO: Ideally, handle this per-tracking.
    items = self.get_items_from_email(email_str)

    try:
      for tracking_number, shipping_status in tracking_nums:
        tqdm.write(f"Tracking: {tracking_number}, Order(s): {order_ids}, "
                   f"Group: {group}, Status: {shipping_status}, Items: {items}")
    except UnicodeEncodeError:
      # TQDM doesn't have great handling for some of the ways the item texts can be encoded, skip it if it fails
      for tracking_number, shipping_status in tracking_nums:
        tqdm.write(f"Tracking: {tracking_number}, Order(s): {order_ids}, "
                   f"Group: {group}, Status: {shipping_status}")

    merchant = self.get_merchant()
    delivery_date = self.get_delivery_date_from_email(email_str)
    trackings = [
        Tracking(tracking_number, group, order_ids, price, to_email, '', date, 0.0, items, merchant,
                 reconcile, delivery_date) for tracking_number, shipping_status in tracking_nums
    ]
    if group is None:
      tqdm.write(f"Could not find buying group from email with order ID(s) {order_ids}")
      return False, trackings
    return True, trackings

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
      status, response = mail.uid('SEARCH', None, seen_filter, f'(SINCE "{date_to_search}")',
                                  *search_terms)
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


def get_email_content(email_id, mail) -> str:
  result, data = mail.uid("FETCH", email_id, "(RFC822)")
  email_str = data[0][1].decode('utf-8')
  # sometimes it's base64 decoded and we need to handle that
  if BASE_64_FLAG in email_str:
    # this is messy, but so is base64 / the email format so yeah
    # '=' is padding in base64, so just keep trying until we get a valid length
    for i in range(4):
      repeated_equals = '=' * i
      try:
        email_str = str(base64.b64decode(email_str.split(BASE_64_FLAG)[-1] + repeated_equals))
        break
      except:
        # possible encoding error (not sure error type), skip
        pass
  return email_str


def clean_email_content(email_str) -> str:
  email_str = email_str.replace('=3D', '=')
  email_str = email_str.replace('=\r\n', '')
  email_str = email_str.replace('\r\n', '')
  email_str = email_str.replace('&amp;', '&')
  email_str = email_str.replace(r'\r', '')
  email_str = email_str.replace(r'\n', '')
  return email_str
