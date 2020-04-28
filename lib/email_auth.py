#!/usr/bin/env python3
#email_auth.py
#
#Combine standard login with option of OAuth2.0
#
from httplib2 import Http
from oauth2client import file, client, tools
from googleapiclient.discovery import build
from lib.config_file import open_config
import smtplib
import base64
from imaplib import IMAP4_SSL


def email_authentication():
   config = open_config()
   email_config = config['email']
   SCOPES = email_config["gmailUrl"]
   username= email_config["username"]
   mail = IMAP4_SSL(email_config['imapUrl'])
   if "password" in email_config:
      mail.login(email_config['username'], email_config['password'])
   else:
      creds = get_oauth_credentials(SCOPES)
      client_credentials = creds.get_access_token().access_token
      authstring = f"user={username}\1auth=Bearer {client_credentials}\1\1"
      mail.authenticate('XOAUTH2', lambda x: authstring)
   return mail


def send_email(self, recipients, message):
  if "password" in self.email_config:
    s = smtplib.SMTP(self.email_config['smtpUrl'],
                     self.email_config['smtpPort'])
    s.starttls()
    s.login(self.email_config['username'], self.email_config['password'])
    s.sendmail(self.email_config['username'], recipients, message.as_string())
    s.quit()
  else:
    config = open_config()
    email_config = config['email']
    SCOPES = email_config["gmailUrl"]
    creds = get_oauth_credentials(SCOPES)
    service = build('gmail','v1',credentials=creds)
    raw = base64.urlsafe_b64encode(message.as_bytes())
    raw = raw.decode()
    body = {'raw': raw}
    message=body
    service.users().messages().send(userId=self.email_config['username'],body=message).execute()


def get_oauth_credentials(SCOPES):
  store = file.Storage('storage.json')
  creds = store.get()
  if not creds or creds.invalid:
    flow = client.flow_from_clientsecrets('client_secret.json', SCOPES)
    creds = tools.run_flow(flow, store)
  else:
    creds.refresh(Http())
  return creds