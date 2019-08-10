import re
import collections
import imaplib
import urllib3
import time

class Tracking:

    def __init__(self, tracking_number, group, order_number, price):
        self.tracking_number = tracking_number
        self.group = group
        self.order_number = order_number
        self.price = price

    def __str__(self):
        return "number: %s, group: %s, order: %s, price: %s" % (self.tracking_number, self.group, self.order_number, self.price)

class TrackingRetriever:

    first_regex = r'.*<a href="(http[^"]*ship-track[^"]*)"'
    second_regex = r'.*<a hr[^"]*=[^"]*"(http[^"]*progress-tracker[^"]*)"'

    order_from_url_regex = r'.*orderId%3D([0-9\-]+)'
    price_regex = r'.*Shipment total:(\$\d+\.\d{2})'

    def __init__(self, config, driver_creator):
        self.config = config
        self.email_config = config['email']
        self.driver_creator = driver_creator

    # If we receive an exception, we should reset all the emails to be unread
    def mark_as_unread(self, email_ids):
        mail = self.get_all_mail_folder()
        for email_id in email_ids:
            mail.uid('STORE', email_id, '-FLAGS', '(\Seen)')

    def get_trackings(self):
        groups_dict = collections.defaultdict(list)
        email_ids = self.get_email_ids()
        try:
            trackings = [self.get_tracking(email_id) for email_id in email_ids]
        except:
            print("Error when parsing emails. Marking emails as unread.")
            self.mark_as_unread(email_ids)
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
        print(raw_email)
        raise Exception("Unknown buying group")

    def get_url_from_email(self, raw_email):
        match = re.match(self.first_regex, str(raw_email))
        if not match:
            match = re.match(self.second_regex, str(raw_email))
        if match: return match.group(1)
        print(raw_email)
        raise Exception("Could not get URL from email")

    def get_order_id_from_url(self, url):
        match = re.match(self.order_from_url_regex, url)
        if match: return match.group(1)
        print(raw_email)
        raise Exception("Could not get order ID from email")

    def get_price_from_email(self, raw_email):
        # Price isn't necessary, so if we can't find it don't raise an exception
        match = re.match(self.price_regex, raw_email)
        if match:
            return match.group(1)
        return ''

    def get_tracking(self, email_id):
        mail = self.get_all_mail_folder()

        result, data = mail.uid("FETCH", email_id, "(RFC822)")
        raw_email = str(data[0][1]).replace("=3D", "=").replace('=\\r\\n', '').replace('\\r\\n', '')
        url = self.get_url_from_email(raw_email)
        price = self.get_price_from_email(raw_email)
        tracking_number = self.get_tracking_info(url)
        group = self.get_buying_group(raw_email)
        order_id = self.get_order_id_from_url(url)
        return Tracking(tracking_number, group, order_id, price)

    def get_tracking_info(self, amazon_url):
        driver = self.load_url(amazon_url)
        try:
            element = driver.find_element_by_xpath("//*[contains(text(), 'Tracking ID')]")
            regex = r'Tracking ID: ([A-Z0-9]+)'
            match = re.match(regex, element.text)
            tracking_number = match.group(1)
            return tracking_number
        except:
            print("Couldn't get tracking ID from url %s" % amazon_url)
            raise
        finally:
            driver.close()

    def load_url(self, url):
        driver = self.driver_creator.new()
        driver.get(url)
        time.sleep(3) # wait for page load because the timeouts can be buggy
        return driver

    def get_all_mail_folder(self):
        mail = imaplib.IMAP4_SSL(self.email_config['imapUrl'])
        mail.login(self.email_config['username'], self.email_config['password'])
        mail.select('"[Gmail]/All Mail"')
        return mail

    def get_email_ids(self):
        mail = self.get_all_mail_folder()
        status, response = mail.uid('SEARCH', None, 'FROM "shipment-tracking@amazon.com"', '(UNSEEN)', '(SUBJECT "shipped")')
        email_ids = response[0].decode('utf-8')

        return email_ids.split()
