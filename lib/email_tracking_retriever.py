import base64
import collections
import concurrent
import datetime
import email
import imaplib
import os
import socket
from abc import ABC, abstractmethod
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Any, Callable, Optional, Tuple, TypeVar, Dict, List, Set

from selenium.webdriver.chrome.webdriver import WebDriver
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

import lib.email_auth as email_auth
from lib import util
from lib.driver_creator import DriverCreator
from lib.tracking import Tracking

_FuncT = TypeVar('_FuncT', bound=Callable)

DEFAULT_PROFILE_BASE = '.profiles'
BASE_64_FLAG = 'Content-Transfer-Encoding: base64'
TODAY = datetime.date.today().strftime('%Y-%m-%d')
MAX_ATTEMPTS = 2
DEFAULT_NUM_WORKERS = 10


def find_login(email_profile_name: str, profile_base: str) -> Optional[WebDriver]:
  # attempt exact matches first
  for profile_name in os.listdir(os.path.expanduser(profile_base)):
    if email_profile_name == profile_name.lower():
      return new_driver(profile_base, profile_name)
  # then go to substrings
  for profile_name in os.listdir(os.path.expanduser(profile_base)):
    if email_profile_name in profile_name.lower():
      return new_driver(profile_base, profile_name)
  return None


class EmailTrackingRetriever(ABC):

  def __init__(self, config, args) -> None:
    self.config = config
    self.email_config = config['email']
    self.args = args
    self.all_email_ids = []

  def back_out_of_all(self) -> None:
    """
    Called when an exception is received. If running in the (default) unseen
    mode, then all processed emails are set to unread again.
    """
    self.mark_emails_as_unread(self.all_email_ids)

  def mark_emails_as_unread(self, email_ids) -> None:
    if not self.args.seen:
      for email_id in tqdm(email_ids, desc="Marking emails as unread...", unit="email"):
        self.mark_as_unread(email_id)

  def mark_as_unread(self, email_id) -> None:
    if not self.args.seen:
      mail = get_all_mail_folder()
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
    if not self.all_email_ids:
      return trackings

    mail = get_all_mail_folder()
    # Emails that throw Exceptions and can't be parsed at all.
    failed_email_ids = []

    try:
      profiles_to_email_infos = retrieve_email_infos(self.all_email_ids, mail)
    except Exception as e:
      print(f"Unexpected error retrieving email infos: "
            f"{e.__class__.__name__}: {str(e)}: {util.get_traceback_lines()}")
      self.mark_emails_as_unread(self.all_email_ids)
      return trackings

    if 'profileBase' in self.config or self.config.get('useProfiles', False):
      num_workers = self.config.get('numWorkers', DEFAULT_NUM_WORKERS)
      base_driver = None
    else:
      num_workers = 1
      base_driver = DriverCreator().new()

    with ThreadPoolExecutor(num_workers) as executor:
      tasks = []
      for email_profile_name, email_dict in profiles_to_email_infos.items():
        tasks.append(
            executor.submit(self.get_trackings_with_profile, base_driver, email_profile_name,
                            email_dict))
      for task in tqdm(
          concurrent.futures.as_completed(tasks),
          desc="Processing profiles ...",
          unit="profile",
          total=len(tasks),
          maxinterval=3):
        new_trackings, new_failed_email_ids = task.result()
        for tracking in new_trackings:
          trackings[tracking.tracking_number] = tracking
        failed_email_ids.extend(new_failed_email_ids)

    if len(failed_email_ids) > 0:
      print(f"Errored out while retrieving {len(failed_email_ids)} trackings "
            f"with email IDs: {failed_email_ids}.")
      if not self.args.seen:
        print("Marking these emails as unread.")
        self.mark_emails_as_unread(failed_email_ids)

    return trackings

  def get_buying_group_from_string(self, string_in_question: str) -> Tuple[Optional[str], bool]:
    string_in_question = string_in_question.upper()
    for group in self.config['groups'].keys():
      group_conf = self.config['groups'][group]
      # An optional "except" list in the config indicates terms that we wish to avoid for this
      # group. If a term is found that's in this list, we will not include this email as part of
      # the group in question. This is useful when two groups share the same address.
      if any([
          str(except_elem).upper() in string_in_question
          for except_elem in group_conf.get('except', [])
      ]):
        continue

      reconcile = bool(group_conf['reconcile']) if 'reconcile' in group_conf else True
      group_keys = group_conf['keys']
      if isinstance(group_keys, str):
        group_keys = [group_keys]
      for group_key in group_keys:
        if str(group_key).upper() in string_in_question:
          return group, reconcile
    return None, True

  def get_buying_group(self, raw_email: str,
                       driver: Optional[WebDriver]) -> Tuple[Optional[str], bool]:
    from_email, reconcile = self.get_buying_group_from_string(raw_email)
    if from_email:
      return from_email, reconcile
    return self.get_buying_group_from_string(
        self.get_address_info_with_webdriver(raw_email, driver))

  @abstractmethod
  def get_address_info_with_webdriver(self, email_str: str,
                                      driver: Optional[WebDriver]) -> Optional[str]:
    pass

  @abstractmethod
  def get_order_ids_from_email(self, raw_email) -> Any:
    pass

  @abstractmethod
  def get_price_from_email(self, raw_email) -> Any:
    pass

  @abstractmethod
  def get_tracking_numbers_from_email(
      self, raw_email, from_email: str, to_email: str,
      driver: Optional[WebDriver]) -> List[Tuple[str, Optional[str]]]:
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

  def get_trackings_with_profile(self, base_driver: Optional[WebDriver], email_profile_name: str,
                                 email_dict: Dict[str, str]) -> Tuple[List[Tracking], List[str]]:
    result: List[Tracking] = []
    failed_email_ids: List[str] = []

    # First, get the driver we're going to use. Create it if we're using profiles.
    # If we're not using profiles, use the same driver for all the emails.
    try:
      if 'profileBase' in self.config or self.config.get('useProfiles', False):
        profile_base = self.config.get('profileBase', DEFAULT_PROFILE_BASE)
        driver = find_login(email_profile_name, profile_base)
      else:
        if base_driver is None:
          raise Exception('Base driver does not exist but we are not using profiles')
        driver = base_driver
    except Exception as e:
      # If driver creation fails, it might be in use or something. Reset entirely.
      print(f"Unexpected error creating driver for profile {email_profile_name}: "
            f"{e.__class__.__name__}: {str(e)}: {util.get_traceback_lines()}")
      failed_email_ids.extend(email_dict.keys())
      return result, failed_email_ids

    try:
      for email_id, email_content in email_dict.items():
        try:
          for attempt in range(MAX_ATTEMPTS):
            try:
              success, new_trackings = self.get_trackings_from_email(email_id, email_content,
                                                                     attempt, driver)
            except (ConnectionError, socket.error, imaplib.IMAP4.abort):
              print(f"Connection lost; reconnecting (attempt {attempt + 1}).")
              # Re-initializing the IMAP connection and retrying should fix most
              # connection-related errors.
              # See https://stackoverflow.com/questions/7575943/eof-error-in-imaplib
              mail = get_all_mail_folder()
              continue
            if success:
              result.extend(new_trackings)
              break
            elif attempt >= MAX_ATTEMPTS - 1:
              print(
                  f"Failed to find tracking number from email after {MAX_ATTEMPTS} retries; we got: {new_trackings}"
              )
              self.mark_as_unread(email_id)
        except Exception as e:
          failed_email_ids.append(email_id)
          print(f"Unexpected error fetching tracking from email ID {email_id}: "
                f"{e.__class__.__name__}: {str(e)}: {util.get_traceback_lines()}")
      return result, failed_email_ids
    except Exception as e:
      raise Exception("Fatal unexpected fatal error when parsing emails") from e
    finally:
      if driver:
        driver.quit()

  def get_trackings_from_email(self, email_id, email_content: str, attempt: int,
                               driver: Optional[WebDriver]) -> Tuple[bool, List[Tracking]]:
    """
    Returns a Tuple of boolean success status and tracking information for a
    given email id. If success is True then the tracking info is complete and
    should be used, otherwise if False then the tracking info is incomplete
    and is only suitable for use as error output.
    """
    msg = email.message_from_string(email_content)

    email_str = clean_email_content(email_content)
    to_email = str(msg['To']).replace('<', '').replace('>', '') if msg['To'] else ''
    from_email = str(msg['From']).replace('<', '').replace(
        '>', '') if msg['From'] else ''  # Also has display name.
    date = datetime.datetime.strptime(
        msg['Date'], '%a, %d %b %Y %H:%M:%S %z').strftime('%Y-%m-%d') if msg['Date'] else TODAY
    price = self.get_price_from_email(email_str)
    order_ids = self.get_order_ids_from_email(email_str)
    group, reconcile = self.get_buying_group(email_str, driver)
    tracking_nums = self.get_tracking_numbers_from_email(email_str, from_email, to_email, driver)

    if len(tracking_nums) == 0:
      incomplete_tracking = Tracking(None, group, order_ids, price, to_email, date, 0.0)
      tqdm.write(f"Could not find tracking number from email {email_id} (attempt {attempt + 1}).")
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
        Tracking(tracking_number, group, order_ids, price, to_email, date, 0.0, items, merchant,
                 reconcile, delivery_date) for tracking_number, shipping_status in tracking_nums
    ]
    if group is None:
      tqdm.write(f"Could not find buying group from email with order ID(s) {order_ids} "
                 f"(attempt {attempt + 1}).")
      return False, trackings
    return True, trackings

  def get_email_ids(self) -> Set[str]:
    date_to_search = self.get_date_to_search()
    mail = get_all_mail_folder()
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


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=120))
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


# Returns Dict[profile_name, Dict[email_id, email_content]]
def retrieve_email_infos(all_email_ids: Set[str],
                         mail: imaplib.IMAP4_SSL) -> Dict[str, Dict[str, str]]:
  result: Dict[str, Dict[str, str]] = collections.defaultdict(dict)
  for email_id in tqdm(
      all_email_ids, desc="Retrieving email information", unit="email", total=len(all_email_ids)):
    email_str = get_email_content(email_id, mail)
    msg = email.message_from_string(email_str)
    to_email = str(msg['To']).replace('<', '').replace('>', '') if msg['To'] else ''
    profile_name = to_email.split("@")[0].lower()
    result[profile_name][email_id] = email_str
  return result


def new_driver(profile_base: str, profile_name: str) -> WebDriver:
  dc = DriverCreator()
  dc.args.no_headless = True
  return dc.new(f"{os.path.expanduser(profile_base)}/{profile_name}")


def get_all_mail_folder() -> imaplib.IMAP4_SSL:
  mail = email_auth.email_authentication()
  mail.select('"[Gmail]/All Mail"')
  return mail
