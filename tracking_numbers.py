import yaml
import re
import collections
import time
import urllib3
import datetime
import smtplib
import imaplib
from selenium import webdriver
from email.mime.text import MIMEText

TODAY = datetime.datetime.now().strftime("%Y-%m-%d")
CONFIG_FILE = "config.yml"

with open(CONFIG_FILE, 'r') as config_file_stream:
    CONFIG = yaml.safe_load(config_file_stream)

EMAIL_CONFIG = CONFIG['email']

"""
TODO:
- use a VPN to hit the amazon URLs from different IPs to avoid associating the accounts together
- repeat for best buy orders?
"""

def get_buying_group(raw_email):
    raw_email = raw_email.upper()
    for group in CONFIG['groups']:
        if group['key'].upper() in raw_email:
            return group['name']
    print(raw_email)
    raise Exception("Unknown buying group")

def get_mail_folder(folder_name):
    mail = imaplib.IMAP4_SSL(EMAIL_CONFIG['imapUrl'])
    mail.login(EMAIL_CONFIG['username'], EMAIL_CONFIG['password'])
    mail.select(folder_name)
    return mail

def get_email_ids(folder_name):
    mail = get_mail_folder(folder_name)
    status, response = mail.search(None, '(UNSEEN)', '(SUBJECT "shipped")')
    email_ids = response[0].decode('utf-8')

    return email_ids.split()

def parse_emails(email_ids):
    first_regex = r'.*<a href="(http[^"]*ship-track[^"]*)"'
    second_regex = r'.*<a hr[^"]*=[^"]*"(http[^"]*progress-tracker[^"]*)"'
    for email_id in email_ids:
        print(email_id)
        mail = get_mail_folder(EMAIL_CONFIG['amazonFolderName'])

        result, data = mail.fetch(bytes(email_id, 'utf-8'), "(RFC822)")
        raw_email = str(data[0][1]).replace("=3D", "=").replace('=\\r\\n', '')
        matches = re.match(first_regex, str(raw_email))
        if not matches:
            matches = re.match(second_regex, str(raw_email))
        yield matches.group(1), get_buying_group(raw_email)

def load_url(url):
    sleep_interval = 5
    for i in range(10):
        try:
            driver = webdriver.Chrome()
            driver.implicitly_wait(10)
            driver.set_page_load_timeout(10)
            driver.get(url)
            time.sleep(5) # wait for page load because the timeouts can be buggy
            return driver
        except urllib3.exceptions.MaxRetryError:
            print("Error, waiting " + str(sleep_interval))
            time.sleep(sleep_interval)
            sleep_interval *= 2
    driver.close()
    raise Error("Too many retries")

def get_tracking_info(amazon_url):
    driver = load_url(amazon_url)
    try:
        found_elements = driver.find_elements_by_xpath("//*[contains(text(), 'Tracking ID')]")
        element = found_elements[0]
        regex = r'Tracking ID: ([A-Z0-9]+)'
        match = re.match(regex, element.text)
        tracking_number = match.group(1)
        return tracking_number
    finally:
        driver.close()

def create_email_content(groups_dict):
    content = "Tracking numbers per group:\n\n"
    for group, numbers in groups_dict.items():
        content += group
        content += '\n'
        content += '\n'.join(numbers)
        content += '\n\n'
    return content

def send_email(email_content):
    s = smtplib.SMTP(EMAIL_CONFIG['smtpUrl'], EMAIL_CONFIG['smtpPort']) 
    s.starttls() 
    s.login(EMAIL_CONFIG['username'], EMAIL_CONFIG['password'])

    message = MIMEText(email_content)
    message['From'] = EMAIL_CONFIG['username']
    message['To'] = EMAIL_CONFIG['username']
    message['Subject'] = "Amazon Tracking Numbers " + TODAY
    s.sendmail(EMAIL_CONFIG['username'], EMAIL_CONFIG['username'], message.as_string())
    s.quit() 

if __name__ == "__main__":
    groups_dict = collections.defaultdict(list)
    email_ids = get_email_ids(CONFIG['amazonFolderName'])
    for amazon_url, buying_group in parse_emails(email_ids):
        print(amazon_url)
        print(buying_group)
        time.sleep(5)
        tracking_number = get_tracking_info(amazon_url)
        print(tracking_number)
        groups_dict[buying_group].append(tracking_number)

    email_content = create_email_content(groups_dict)
    send_email(email_content)


