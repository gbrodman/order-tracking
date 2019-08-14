import googleapiclient.errors
import re
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
        valueInputOption="USER_ENTERED",
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

  def _create_hyperlink(self, tracking):
    link = self._get_tracking_url(tracking)
    if link == None:
      return tracking.tracking_number
    return '=HYPERLINK("%s", "%s")' % (link, tracking.tracking_number)

  def _get_tracking_url(self, tracking):
    number = tracking.tracking_number
    if number.startswith("TBA"):  # Amazon
      return tracking.url
    elif number.startswith("1Z"):  # UPS
      return "https://www.ups.com/track?loc=en_US&tracknum=%s" % number
    elif len(number) == 12 or len(number) == 15:  # FedEx
      return "https://www.fedex.com/apps/fedextrack/?tracknumbers=%s" % number
    elif len(number) == 22:  # USPS
      return "https://tools.usps.com/go/TrackConfirmAction?qtc_tLabels1=%s" % number
    else:
      print("Unknown tracking number type: %s" % number)
      return None

  def _create_row_data(self, tracking):
    return [
        self._create_hyperlink(tracking), ", ".join(tracking.order_ids),
        tracking.price, tracking.to_email
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
