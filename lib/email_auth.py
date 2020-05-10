# email_auth.py
#
# Combine standard login with option of OAuth2.0
#

import smtplib
import base64
from httplib2 import Http
from oauth2client import file, client, tools
from googleapiclient.discovery import build
from lib.config import open_config
from imaplib import IMAP4_SSL

config = open_config()
email_config = config['email']
gmail_url = "https://mail.google.com/"
imapUrl = "imap.gmail.com"
smtpUrl = "smtp.gmail.com"
smtpPort = "587"
username= email_config["username"]


def email_authentication():
   
  mail = IMAP4_SSL(imapUrl)
  if "password"  in email_config and email_config["password"]:
    mail.login(email_config['username'], email_config['password'])
  else:
    creds = get_oauth_credentials(gmail_url)
    client_credentials = creds.get_access_token().access_token
    authstring = f"user={username}\1auth=Bearer {client_credentials}\1\1"
    mail.authenticate('XOAUTH2', lambda x: authstring)
  return mail


def send_email(recipients, message):
  if "password"  in email_config and email_config["password"]:
    s = smtplib.SMTP(smtpUrl,
                     smtpPort)
    s.starttls()
    s.login(email_config['username'], email_config['password'])
    s.sendmail(email_config['username'], recipients, message.as_string())
    s.quit()
  else:
    creds = get_oauth_credentials(gmail_url)
    service = build('gmail','v1',credentials=creds)
    raw = base64.urlsafe_b64encode(message.as_bytes())
    raw = raw.decode()
    body = {'raw': raw}
    message=body
    service.users().messages().send(userId=self.email_config['username'],body=message).execute()


def get_oauth_credentials():
  store = file.Storage('storage.json')
  creds = store.get()
  if not creds or creds.invalid:
    flow = client.flow_from_clientsecrets('client_secret.json', gmail_url)
    creds = tools.run_flow(flow, store)
  else:
    creds.refresh(Http())
  return creds
