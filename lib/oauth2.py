#!/usr/bin/env python3
#Complete OAuth2.0
#
from httplib2 import Http
from oauth2client import file, client, tools
import yaml
import json
from imaplib import IMAP4_SSL
def authentication():
   SCOPES = 'https://mail.google.com/'
   CONFIG_FILE = "config.yml"
   with open(CONFIG_FILE, 'r') as config_file_stream:
       config = yaml.safe_load(config_file_stream)
       email_config = config['email']
   mail = IMAP4_SSL(email_config['imapUrl'])
   store = file.Storage('storage.json')
   creds = store.get()

   if not creds or creds.invalid:
       flow = client.flow_from_clientsecrets('client_secret.json', SCOPES)
       creds = tools.run_flow(flow, store)
       client_credentials = creds.get_access_token().access_token
   else:
      creds.refresh(Http())
      client_credentials = creds.get_access_token().access_token
   authstring = "user=%s\1auth=Bearer %s\1\1" % (email_config["username"], client_credentials)
   mail.authenticate('XOAUTH2', lambda x: authstring)
   return mail
def getAuthString():
   CONFIG_FILE = "config.yml"
   with open(CONFIG_FILE, 'r') as config_file_stream:
      config = yaml.safe_load(config_file_stream)
      email_config = config['email']
   store = file.Storage('storage.json')
   creds = store.get()
   if not creds or creds.invalid:
      flow = client.flow_from_clientsecrets('client_secret.json', SCOPES)
      creds = tools.run_flow(flow, store)
      client_credentials = creds.get_access_token().access_token
   else:
      creds.refresh(Http())
      client_credentials = creds.get_access_token().access_token
   return creds
