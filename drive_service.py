from googleapiclient.discovery import build
from google.oauth2 import service_account
from typing import Any

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def create_sheets() -> Any:
  return _create("sheets", "v4")


def _create(service, version):
  credentials = service_account.Credentials.from_service_account_file(
      'creds.json', scopes=SCOPES)
  return build(service, version, credentials=credentials)
