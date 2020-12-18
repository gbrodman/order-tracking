# email_auth.py
#
# Combine standard login with option of OAuth2.0
#

import base64
import smtplib
from imaplib import IMAP4_SSL

from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools

from lib.config import open_config

CONFIG = open_config()
EMAIL_CONFIG = CONFIG['email']
GMAIL_URL = "https://mail.google.com/"
IMAPURL = "imap.gmail.com"
SMTPURL = "smtp.gmail.com"
SMTPPORT = "587"
USERNAME = EMAIL_CONFIG["username"]


def email_authentication() -> IMAP4_SSL:
  mail = IMAP4_SSL(IMAPURL)
  if "password" in EMAIL_CONFIG and EMAIL_CONFIG["password"]:
    mail.login(EMAIL_CONFIG['username'], EMAIL_CONFIG['password'])
  else:
    creds = get_oauth_credentials()
    client_credentials = creds.get_access_token().access_token
    authstring = f"user={USERNAME}\1auth=Bearer {client_credentials}\1\1"
    mail.authenticate('XOAUTH2', lambda x: authstring)
  return mail


def send_email(recipients, message):
  if "password" in EMAIL_CONFIG and EMAIL_CONFIG["password"]:
    s = smtplib.SMTP(SMTPURL, SMTPPORT)
    s.starttls()
    s.login(EMAIL_CONFIG['username'], EMAIL_CONFIG['password'])
    s.sendmail(EMAIL_CONFIG['username'], recipients, message.as_string())
    s.quit()
  else:
    creds = get_oauth_credentials()
    service = build('gmail', 'v1', credentials=creds)
    raw = base64.urlsafe_b64encode(message.as_bytes())
    raw = raw.decode()
    body = {'raw': raw}
    message = body
    service.users().messages().send(userId=EMAIL_CONFIG['username'], body=message).execute()


def get_oauth_credentials():
  store = file.Storage(EMAIL_CONFIG['storage'])
  creds = store.get()
  if not creds or creds.invalid:
    flow = client.flow_from_clientsecrets(EMAIL_CONFIG['client_secret'], GMAIL_URL)
    creds = tools.run_flow(flow, store)
  else:
    creds.refresh(Http())
  return creds
