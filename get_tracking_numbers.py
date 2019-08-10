import yaml
import sys
import traceback
import upload_tracking_numbers
from email_sender import EmailSender
from tracking_retriever import TrackingRetriever
from driver_creator import DriverCreator

CONFIG_FILE = "config.yml"

with open(CONFIG_FILE, 'r') as config_file_stream:
    CONFIG = yaml.safe_load(config_file_stream)

EMAIL_CONFIG = CONFIG['email']

DRIVER_CREATOR = None

def send_error_email(email_sender, subject, exception):
    type, value, trace = sys.exc_info()
    formatted_trace = traceback.format_tb(trace)
    lines = [str(type), str(value)] + formatted_trace
    email_sender.send_email_content(subject, "\n".join(lines))

def upload_numbers(email_sender, groups_dict):
    for group, trackings in groups_dict.items():
        numbers = [tracking.tracking_number for tracking in trackings]
        group_config = CONFIG['groups'][group]
        if group_config.get('password'):
            try:
                upload_tracking_numbers.upload(numbers, group, group_config['username'], group_config['password'], DRIVER_CREATOR)
            except Exception as e:
                send_error_email(email_sender, "Error uploading tracking numbers", e)
                raise e

if __name__ == "__main__":
    if len(sys.argv) > 1:
        DRIVER_CREATOR = DriverCreator(sys.argv[1].upper())
    else:
        DRIVER_CREATOR = DriverCreator("CHROME")

    email_sender = EmailSender(EMAIL_CONFIG)
    tracking_retriever = TrackingRetriever(CONFIG, DRIVER_CREATOR)
    try:
        groups_dict = tracking_retriever.get_trackings()
    except Exception as e:
        send_error_email(email_sender, "Error retrieving emails", e)
        raise e

    email_sender.send_email(groups_dict)
    upload_numbers(email_sender, groups_dict)
