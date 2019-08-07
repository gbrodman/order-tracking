import yaml
import sys
import datetime
import smtplib
import upload_tracking_numbers
from tracking_retriever import TrackingRetriever
from driver_creator import DriverCreator
from email.mime.text import MIMEText

TODAY = datetime.datetime.now().strftime("%Y-%m-%d")
CONFIG_FILE = "config.yml"

with open(CONFIG_FILE, 'r') as config_file_stream:
    CONFIG = yaml.safe_load(config_file_stream)

EMAIL_CONFIG = CONFIG['email']

DRIVER_CREATOR = None

def create_email_content(groups_dict):
    content = "Tracking numbers per group:\n\n"
    for group, trackings in groups_dict.items():
        numbers = [tracking.tracking_number for tracking in trackings]
        content += group
        content += '\n'
        content += '\n'.join(numbers)
        content += '\n\n'
    return content

def upload_numbers(groups_dict):
    for group, trackings in groups_dict.items():
        numbers = [tracking.tracking_number for tracking in trackings]
        group_config = CONFIG['groups'][group]
        if group_config.get('password'):
            try:
                upload_tracking_numbers.upload(numbers, group, group_config['username'], group_config['password'], DRIVER_CREATOR)
            except Exception as e:
                send_email("Error uploading tracking numbers", str(e))

def send_email(subject, content):
    s = smtplib.SMTP(EMAIL_CONFIG['smtpUrl'], EMAIL_CONFIG['smtpPort']) 
    s.starttls() 
    s.login(EMAIL_CONFIG['username'], EMAIL_CONFIG['password'])

    message = MIMEText(content)
    message['From'] = EMAIL_CONFIG['username']
    message['To'] = EMAIL_CONFIG['username']
    message['Subject'] = subject
    s.sendmail(EMAIL_CONFIG['username'], EMAIL_CONFIG['username'], message.as_string())
    s.quit() 

if __name__ == "__main__":
    if len(sys.argv) > 1:
        DRIVER_CREATOR = DriverCreator(sys.argv[1].upper())
    else:
        DRIVER_CREATOR = DriverCreator("CHROME")

    tracking_retriever = TrackingRetriever(CONFIG, DRIVER_CREATOR)
    groups_dict = tracking_retriever.get_trackings()

    email_content = create_email_content(groups_dict)
    send_email("Amazon Tracking Numbers " + TODAY, email_content)

    upload_numbers(groups_dict)


