import datetime
import email
import imaplib
from abc import ABC, abstractmethod
from lib.tracking import Tracking
import lib.tracking
from typing import Any, Callable, Optional, TypeVar

_FuncT = TypeVar('_FuncT', bound=Callable)


class EmailTrackingRetriever(ABC):

  def __init__(self, config, driver_creator) -> None:
    self.config = config
    self.email_config = config['email']
    self.driver_creator = driver_creator
    self.failed_email_ids = []
    self.all_email_ids = []

  # If we receive an exception, we should reset all the emails to be unread
  def back_out_of_all(self) -> None:
    for email_id in self.all_email_ids:
      self.mark_as_unread(email_id)

  def mark_as_unread(self, email_id) -> None:
    mail = self.get_all_mail_folder()
    mail.uid('STORE', email_id, '-FLAGS', '(\Seen)')

  def get_trackings(self) -> list:
    self.all_email_ids = self.get_email_ids()
    print("Found %d unread shipping emails in the dates we searched" %
          len(self.all_email_ids))
    try:
      trackings = [
          self.get_tracking(email_id) for email_id in self.all_email_ids
      ]
      trackings = [tracking for tracking in trackings if tracking]
    except:
      print("Error when parsing emails. Marking emails as unread.")
      self.back_out_of_all()
      raise
    return trackings

  def get_buying_group(self, raw_email) -> Any:
    raw_email = raw_email.upper()
    for group in self.config['groups'].keys():
      group_keys = self.config['groups'][group]['keys']
      if isinstance(group_keys, str):
        group_keys = [group_keys]
      for group_key in group_keys:
        if str(group_key).upper() in raw_email:
          return group
    return None

  @abstractmethod
  def get_order_ids_from_email(self, raw_email) -> Any:
    pass

  @abstractmethod
  def get_price_from_email(self, raw_email) -> Any:
    pass

  @abstractmethod
  def get_tracking_number_from_email(self, raw_email) -> Any:
    pass

  @abstractmethod
  def get_subject_searches(self) -> Any:
    pass

  @abstractmethod
  def get_merchant(self) -> str:
    pass

  @abstractmethod
  def get_order_url_from_email(self, raw_email) -> Any:
    pass

  @abstractmethod
  def get_items_from_email(self, data) -> Any:
    pass

  def get_date_from_msg(self, data) -> str:
    msg = email.message_from_string(str(data[0][1], 'utf-8'))
    msg_date = msg['Date']
    return datetime.datetime.strptime(
        msg_date, '%a, %d %b %Y %H:%M:%S %z').strftime('%Y-%m-%d')

  def get_to_address(self, data) -> str:
    msg = email.message_from_string(str(data[0][1], 'utf-8'))
    return str(msg['To']).replace('<', '').replace('>', '')

  def get_tracking(self, email_id) -> Any:
    mail = self.get_all_mail_folder()

    result, data = mail.uid("FETCH", email_id, "(RFC822)")
    raw_email = str(data[0][1]).replace("=3D",
                                        "=").replace('=\\r\\n', '').replace(
                                            '\\r\\n', '').replace('&amp;', '&')
    to_email = self.get_to_address(data)
    date = self.get_date_from_msg(data)
    url = self.get_order_url_from_email(raw_email)
    price = self.get_price_from_email(raw_email)
    order_ids = self.get_order_ids_from_email(raw_email)
    group = self.get_buying_group(raw_email)
    tracking_number = self.get_tracking_number_from_email(raw_email)
    print("Tracking: %s, Order(s): %s, Group: %s" %
          (tracking_number, ",".join(order_ids), group))
    if tracking_number == None:
      self.failed_email_ids.append(email_id)
      print("Could not find tracking number from email with order(s) %s" %
            order_ids)
      self.mark_as_unread(email_id)
      return None

    items = self.get_items_from_email(data)
    if group == None:
      self.failed_email_ids.append(email_id)
      print("Could not find buying group for email with order(s) %s" %
            order_ids)
      self.mark_as_unread(email_id)
      return None

    merchant = self.get_merchant()
    return Tracking(tracking_number, group, order_ids, price, to_email, url,
                    date, 0.0, items, merchant)

  def get_all_mail_folder(self) -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(self.email_config['imapUrl'])
    mail.login(self.email_config['username'], self.email_config['password'])
    mail.select('"[Gmail]/All Mail"')
    return mail

  def get_email_ids(self) -> Any:
    date_to_search = self.get_date_to_search()
    mail = self.get_all_mail_folder()
    subject_searches = self.get_subject_searches()

    result = set()
    for search_terms in subject_searches:
      search_terms = ['(SUBJECT "%s")' % phrase for phrase in search_terms]
      status, response = mail.uid('SEARCH', None, '(UNSEEN)',
                                  '(SINCE "%s")' % date_to_search,
                                  *search_terms)
      email_ids = response[0].decode('utf-8')
      result.update(email_ids.split())

    return result

  def get_date_to_search(self) -> str:
    if "lookbackDays" in self.config:
      lookback_days = int(self.config['lookbackDays'])
    else:
      lookback_days = 45
    date = datetime.date.today() - datetime.timedelta(days=lookback_days)
    string_date = date.strftime("%d-%b-%Y")
    print("Searching for emails since %s" % string_date)
    return string_date
