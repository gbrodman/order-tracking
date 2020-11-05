import concurrent
import datetime
import email
import os
import sys
import webbrowser
from concurrent.futures.thread import ThreadPoolExecutor
from imaplib import IMAP4_SSL
from typing import List, Dict, Set, Tuple

from tqdm import tqdm

from lib import email_auth
from lib.config import open_config
from lib.debounce import debounce
from lib.email_tracking_retriever import new_driver
from lib.object_retriever import ObjectRetriever
from manual_input import get_required_from_options

ORDERS_URL = 'https://smile.amazon.com/gp/your-account/order-history/ref=ppx_yo_dt_b_oo_view_all?ie=UTF8&orderFilter=open'
DEFAULT_PROFILE_BASE = '.profiles'
EMAIL_ID_TO_EMAIL_ADDRESS_FILENAME = 'email_id_to_email_address.pickle'
DEFAULT_NUM_WORKERS = 10
config = open_config()


class EmailAddressRetriever:
  """
  Parses and caches a map from email_id -> email address (to-address) to guess what profiles should exist
  """

  def __init__(self, config_obj):
    self.retriever = ObjectRetriever(config_obj)
    self.email_id_to_email_address: Dict[str, str] = self.retriever.load(
        EMAIL_ID_TO_EMAIL_ADDRESS_FILENAME)

  @debounce(2)
  def flush(self) -> None:
    self.retriever.flush(self.email_id_to_email_address, EMAIL_ID_TO_EMAIL_ADDRESS_FILENAME)

  def get_email_address(self, mail: IMAP4_SSL, email_id: str) -> str:
    if email_id not in self.email_id_to_email_address:
      _, data = mail.uid("FETCH", email_id, "(RFC822)")
      msg = email.message_from_string(str(data[0][1], 'utf-8'))
      to_email = str(msg['To']).replace('<', '').replace('>', '') if msg['To'] else ''
      self.email_id_to_email_address[email_id] = to_email.lower()
      self.flush()
    return self.email_id_to_email_address[email_id]


def get_order_email_ids(mail: IMAP4_SSL) -> List[str]:
  date = datetime.date.today() - datetime.timedelta(days=45)
  date_to_search = date.strftime("%d-%b-%Y")
  status, response = mail.uid('SEARCH', None, f'(SINCE "{date_to_search}")',
                              '(FROM "auto-confirm@amazon.com")')
  return response[0].decode('utf-8').split()


def load_email_addresses() -> Set[str]:
  mail = load_mail()
  email_address_retriever = EmailAddressRetriever(config)
  email_ids = get_order_email_ids(mail)
  result = set()
  for email_id in tqdm(email_ids, desc='Loading email addresses...', unit='email'):
    result.add(email_address_retriever.get_email_address(mail, email_id))
  return result


def load_mail() -> IMAP4_SSL:
  mail = email_auth.email_authentication()
  mail.select('"[Gmail]/All Mail"')
  return mail


def get_profile_base() -> str:
  base = config['profileBase'] if 'profileBase' in config else DEFAULT_PROFILE_BASE
  base = os.path.expanduser(base)
  if not os.path.exists(base):
    os.mkdir(base)
  return os.path.expanduser(base)


def profile_from_email(email_address: str) -> str:
  return email_address.split('@')[0] if 'profileBase' in config else email_address


def attempt_login(profile_base: str, email_address: str) -> Tuple[str, bool]:
  profile_name = profile_from_email(email_address)
  driver = new_driver(profile_base, profile_name)
  try:
    driver.implicitly_wait(3)
    driver.get(ORDERS_URL)
    success = True if driver.find_elements_by_id('ordersContainer') else False
    return email_address, success
  finally:
    driver.quit()


def find_failed_logins(profile_base: str, email_addresses: Set[str]) -> List[str]:
  failed_emails = []
  num_workers = config['numWorkers'] if 'numWorkers' in config else DEFAULT_NUM_WORKERS
  with ThreadPoolExecutor(num_workers) as executor:
    tasks = []
    for email_address in email_addresses:
      tasks.append(executor.submit(attempt_login, profile_base, email_address))
    for task in tqdm(
        concurrent.futures.as_completed(tasks),
        desc="Attempting logins...",
        unit="email",
        total=len(email_addresses)):
      email_address, success = task.result()
      if not success:
        failed_emails.append(email_address)
  return failed_emails


def get_chrome_command(profile_path):
  if sys.platform.startswith('darwin'):  # osx
    chrome_path = os.path.join(os.getcwd(), "chrome", "osx", "Chromium.app", "Contents", "MacOS",
                               "Chromium")
    return f'"{chrome_path}" %s --user-data-dir="{profile_path}" &'
  elif sys.platform.startswith('win'):  # windows
    chrome_path = os.path.join(os.getcwd(), "chrome", "windows", "chrome-win32", "chrome.exe")
    return f'"{chrome_path}" %s --user-data-dir="{profile_path}" &'
  elif sys.platform == 'linux':
    return f'/usr/bin/google-chrome --user-data-dir="{profile_path}" %s &'
  else:
    raise Exception(f'Unsupported platform: {sys.platform}')


def run_through_failed_logins(profile_base: str, failed_logins: List[str]):
  print('''
  Some logins failed. We will open those one at a time, and you should attempt to log in. For each, input whether or not
  the login was successful. A successful login is one that doesn't require CAPTCHA/OTP, or one that has an OTP with
  or without a CAPTCHA. If it kicks you back to the login screen and has a CAPTCHA on the login screen, that login is
  NOT SUCCESSFUL. 
  ''')
  failed_logins.sort()
  for email_address in failed_logins:
    print(f'Opening profile for {email_address}')
    profile_name = profile_from_email(email_address)
    full_path = f"{os.path.expanduser(profile_base)}/{profile_name}"
    command = get_chrome_command(full_path)
    webbrowser.get(command).open(ORDERS_URL)
    result = get_required_from_options('Was the login successful? ', ['y', 'n'])
    if result == 'n':
      print('\nPlease wait at least two hours then run this again.')
      return
  print(
      'All logins complete. Please wait two hours and try this script again to make sure all stay logged in.'
  )


if __name__ == '__main__':
  print('''
  This is a script to log in to relevant Amazon accounts for shipment information retrieval. The script will search 
  through your emails for relevant email addresses, then attempt to open up a Chrome profile for each email address 
  we found. It will open up many Chrome windows first -- let it run.
  
  After it is done opening and closing Chrome windows, it will let you know whether or not it was successful.
  "Successful" here means that all profiles were logged in to the proper account and you are good to run the
  get_tracking_numbers.py script.
  
  If it's not successful, it will open up login pages on profiles one at a time. It will print out the email address
  that it is using, and you should log in to that account in the Chrome window that it opens. When logging in, Amazon
  may or may not ask you for an OTP/email verification. If so, this is fine. Amazon may even ask you for a CAPTCHA
  when sending an OTP/email verification -- this is also fine. However, if Amazon kicks you back to the password
  entry screen and asks you to fill out a CAPTCHA on the password entry screen, they're rate-limiting you and you
  need to take a break for 2 hours, and re-run the script later.
  
  For each profile, the script will ask you if the login was successful. A successful login means that you were able
  to log in without the aforementioned Amazon-kicking-you-back-to-password-entry-screen. A failed login is when
  they kick you back to the password entry screen and ask for a CAPTCHA there. 
    ''')
  input('Press ENTER to continue ')
  email_addresses = load_email_addresses()
  profile_base = get_profile_base()
  failed_logins = find_failed_logins(profile_base, email_addresses)
  print(f"Total email addresses: {len(email_addresses)}")
  print(f"Non-logged-in email addresses: {len(failed_logins)}")
  if failed_logins:
    run_through_failed_logins(profile_base, failed_logins)
  else:
    print('All logins successful -- proceed to get_tracking_numbers.py')
