import googleapiclient.errors
import re
import sheets_service
import tracking
from objects_to_sheet import ObjectsToSheet


class SheetsUploader:

  def __init__(self, config):
    self.config = config
    if self.is_enabled():
      self.objects_to_sheet = ObjectsToSheet()
      self.service = sheets_service.create()

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
    existing_trackings = self.objects_to_sheet.download_from_sheet(
        tracking.from_row, self.base_spreadsheet_id, group_sheet_id)
    existing_tracking_numbers = set([
        existing_tracking.tracking_number
        for existing_tracking in existing_trackings
    ])

    new_trackings = [
        tracking for tracking in trackings
        if tracking.tracking_number not in existing_tracking_numbers
    ]

    all_trackings = existing_trackings + new_trackings
    self.objects_to_sheet.upload_to_sheet(all_trackings,
                                          self.base_spreadsheet_id,
                                          group_sheet_id)
