import yaml
import sys
import traceback
import upload_tracking_numbers
from email_sender import EmailSender
from tracking_retriever import TrackingRetriever
from driver_creator import DriverCreator

CONFIG_FILE = "config.yml"

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
        driver_creator = DriverCreator(sys.argv[1].upper())
    else:
        driver_creator = DriverCreator("CHROME")

    with open(CONFIG_FILE, 'r') as config_file_stream:
        config = yaml.safe_load(config_file_stream)
    email_config = config['email']

    email_sender = EmailSender(email_config)
    tracking_retriever = TrackingRetriever(config, driver_creator)

    try:
        groups_dict = tracking_retriever.get_trackings()
    except Exception as e:
        send_error_email(email_sender, "Error retrieving emails", e)
        raise e

    email_sender.send_email(groups_dict)
    upload_numbers(email_sender, groups_dict)
