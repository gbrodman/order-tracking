import yaml
import sys
import traceback
import upload_tracking_numbers
from email_sender import EmailSender
from amazon_tracking_retriever import AmazonTrackingRetriever
from driver_creator import DriverCreator
from upload_tracking_numbers import Uploader
from sheets_uploader import SheetsUploader

CONFIG_FILE = "config.yml"

def send_error_email(email_sender, subject):
    type, value, trace = sys.exc_info()
    formatted_trace = traceback.format_tb(trace)
    lines = [str(type), str(value)] + formatted_trace
    email_sender.send_email_content(subject, "\n".join(lines))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        driver_creator = DriverCreator(sys.argv[1].upper())
    else:
        driver_creator = DriverCreator("CHROME")

    with open(CONFIG_FILE, 'r') as config_file_stream:
        config = yaml.safe_load(config_file_stream)
    email_config = config['email']
    email_sender = EmailSender(email_config)

    amazon_tracking_retriever = AmazonTrackingRetriever(config, driver_creator)
    try:
        groups_dict = amazon_tracking_retriever.get_trackings()
    except:
        send_error_email(email_sender, "Error retrieving emails")
        raise

    email_sender.send_email(groups_dict)

    uploader = Uploader(config, driver_creator)
    try:
        uploader.upload(groups_dict)
    except:
        send_error_email(email_sender, "Error uploading tracking numbers")
        raise

    sheets_uploader = SheetsUploader(config)
    try:
        sheets_uploader.upload(groups_dict)
    except:
        send_error_email(email_sender, "Error uploading to Google Sheets")
        raise

