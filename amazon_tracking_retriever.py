import re
import collections
import imaplib
import urllib3
import time
import datetime
import email
from tracking import Tracking


class AmazonTrackingRetriever:

  first_regex = r'.*<a href="(http[^"]*ship-?track[^"]*)"'
  second_regex = r'.*<a hr[^"]*=[^"]*"(http[^"]*progress-tracker[^"]*)"'
  price_regex = r'.*Shipment total:(\$\d+\.\d{2})'
  order_ids_regex = r'#(\d{3}-\d{7}-\d{7})'

  def __init__(self, config, driver_creator):
    self.config = config
    self.email_config = config['email']
    self.driver_creator = driver_creator
    self.failed_email_ids = []

  # If we receive an exception, we should reset all the emails to be unread
  def back_out_of_all(self):
    for email_id in self.all_email_ids:
      self.mark_as_unread(email_id)

  def mark_as_unread(self, email_id):
    mail = self.get_all_mail_folder()
    mail.uid('STORE', email_id, '-FLAGS', '(\Seen)')

  def get_trackings(self):
    groups_dict = collections.defaultdict(list)
    self.all_email_ids = self.get_email_ids()
    print("Found %d unread Amazon shipping emails in the dates we searched" %
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

    for tracking in trackings:
      groups_dict[tracking.group].append(tracking)
    return groups_dict

  def get_buying_group(self, raw_email):
    raw_email = raw_email.upper()
    for group in self.config['groups'].keys():
      group_keys = self.config['groups'][group]['keys']
      if isinstance(group_keys, str):
        group_keys = [group_keys]
      for group_key in group_keys:
        if str(group_key).upper() in raw_email:
          return group
    return None

  def get_url_from_email(self, raw_email):
    match = re.match(self.first_regex, str(raw_email))
    if not match:
      match = re.match(self.second_regex, str(raw_email))
    if match:
      return match.group(1)
    print(raw_email)
    raise Exception("Could not get URL from email")

  def get_order_ids_from_email(self, raw_email):
    matches = re.findall(self.order_ids_regex, raw_email)
    return list(set(matches))

  def get_price_from_email(self, raw_email):
    # Price isn't necessary, so if we can't find it don't raise an exception
    match = re.match(self.price_regex, raw_email)
    if match:
      return match.group(1)
    return ''

  def get_to_address(self, data):
    msg = email.message_from_string(str(data[0][1], 'utf-8'))
    return msg['To']

  def get_tracking(self, email_id):
    mail = self.get_all_mail_folder()

    result, data = mail.uid("FETCH", email_id, "(RFC822)")
    raw_email = str(data[0][1]).replace("=3D",
                                        "=").replace('=\\r\\n', '').replace(
                                            '\\r\\n', '').replace('&amp;', '&')
    to_email = self.get_to_address(data)
    url = self.get_url_from_email(raw_email)
    price = self.get_price_from_email(raw_email)
    tracking_number = self.get_tracking_info(url)
    if tracking_number == None:
      self.failed_email_ids.append(email_id)
      print("Could not find tracking number from URL %s" % url)
      self.mark_as_unread(email_id)
      return None

    order_ids = self.get_order_ids_from_email(raw_email)
    group = self.get_buying_group(raw_email)
    if group == None:
      self.failed_email_ids.append(email_id)
      print("Could not find buying group for order ID %s" % order_ids)
      self.mark_as_unread(email_id)
      return None

    return Tracking(tracking_number, group, order_ids, price, to_email, url)

  def get_tracking_info(self, amazon_url):
    driver = self.load_url(amazon_url)
    try:
      element = driver.find_element_by_xpath(
          "//*[contains(text(), 'Tracking ID')]")
      regex = r'Tracking ID: ([a-zA-Z0-9]+)'
      match = re.match(regex, element.text)
      tracking_number = match.group(1)
      return tracking_number
    except:
      # swallow this and continue on
      return None
    finally:
      driver.close()

  def load_url(self, url):
    driver = self.driver_creator.new()
    driver.get(url)
    time.sleep(3)  # wait for page load because the timeouts can be buggy
    return driver

  def get_all_mail_folder(self):
    mail = imaplib.IMAP4_SSL(self.email_config['imapUrl'])
    mail.login(self.email_config['username'], self.email_config['password'])
    mail.select('"[Gmail]/All Mail"')
    return mail

  def get_email_ids(self):
    date_to_search = self.get_date_to_search()
    mail = self.get_all_mail_folder()
    status, response = mail.uid('SEARCH', None,
                                'FROM "shipment-tracking@amazon.com"',
                                '(UNSEEN)', '(SUBJECT "shipped")',
                                '(SINCE "%s")' % date_to_search)
    email_ids = response[0].decode('utf-8')

    return email_ids.split()

  def get_date_to_search(self):
    if "lookbackDays" in self.config:
      lookback_days = int(self.config['lookbackDays'])
    else:
      lookback_days = 30
    date = datetime.date.today() - datetime.timedelta(days=lookback_days)
    string_date = date.strftime("%d-%b-%Y")
    print("Searching for emails since %s" % string_date)
    return string_date
