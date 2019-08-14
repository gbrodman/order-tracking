import googleapiclient.errors
from googleapiclient.discovery import build
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsUploader:

  def __init__(self, config):
    self.config = config
    if self.is_enabled():
      self.service = self.create_service()

  def create_service(self):
    credentials = service_account.Credentials.from_service_account_file(
        'creds.json', scopes=SCOPES)
    return build('sheets', 'v4', credentials=credentials)

  def upload(self, groups_dict):
    if not self.is_enabled():
      return

    for group, trackings in groups_dict.items():
      if group not in self.sheet_ids:
        continue
      group_sheet_id = self.sheet_ids[group]
      self.upload_trackings(group_sheet_id, trackings)

  def is_enabled(self):
    if "googleSheets" not in self.config:
      return False
    sheets_config = self.config["googleSheets"]
    if "baseSpreadsheetId" not in sheets_config:
      return False
    base_spreadsheet_id = sheets_config["baseSpreadsheetId"]
    if not base_spreadsheet_id:
      return False
    if "sheetIds" not in sheets_config:
      return False

    self.base_spreadsheet_id = base_spreadsheet_id
    self.sheet_ids = sheets_config["sheetIds"]
    return True

  def upload_trackings(self, group_sheet_id, trackings):
    trackings = self._find_new_trackings(group_sheet_id, trackings)
    values = [self._create_row_data(tracking) for tracking in trackings]
    body = {"values": values}
    self.service.spreadsheets().values().append(
        spreadsheetId=self.base_spreadsheet_id,
        range=group_sheet_id + "!A1:A1",
        valueInputOption="RAW",
        body=body).execute()

  def _find_new_trackings(self, group_sheet_id, trackings):
    range_name = group_sheet_id + "!A1:A"
    try:
      existing_values_result = self.service.spreadsheets().values().get(
          spreadsheetId=self.base_spreadsheet_id, range=range_name).execute()
    except googleapiclient.errors.HttpError:
      # sheet probably doesn't exist
      self._create_sheet(group_sheet_id)
      existing_values_result = self.service.spreadsheets().values().get(
          spreadsheetId=self.base_spreadsheet_id, range=range_name).execute()

    if 'values' not in existing_values_result:
      return trackings
    existing_tracking_numbers = set(
        [value[0] for value in existing_values_result['values']])
    return [
        tracking for tracking in trackings
        if tracking.tracking_number not in existing_tracking_numbers
    ]

  def _create_row_data(self, tracking):
    return [
        tracking.tracking_number, tracking.order_number, tracking.price,
        tracking.to_email
    ]

  def _write_header(self, group_sheet_id):
    header = ["Tracking Number", "Order Number(s)", "Price", "To Email"]
    values = [header]
    body = {"values": values}
    self.service.spreadsheets().values().append(
        spreadsheetId=self.base_spreadsheet_id,
        range=group_sheet_id + "!A1:A1",
        valueInputOption="RAW",
        body=body).execute()

  def _create_sheet(self, group_sheet_id):
    batch_update_body = {
        'requests': [{
            'addSheet': {
                'properties': {
                    'title': group_sheet_id
                }
            }
        }]
    }
    self.service.spreadsheets().batchUpdate(
        spreadsheetId=self.base_spreadsheet_id,
        body=batch_update_body).execute()
    self._write_header(group_sheet_id)
