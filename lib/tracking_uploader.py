from datetime import date, timedelta
from typing import List

from lib import tracking
from lib.objects_to_sheet import ObjectsToSheet


class TrackingUploader:

  def __init__(self, config) -> None:
    self.config = config
    self.objects_to_sheet = ObjectsToSheet()
    self.base_spreadsheet_id = config['reconciliation']['baseSpreadsheetId']

  def upload_trackings(self, trackings) -> None:
    existing_trackings = self.objects_to_sheet.download_from_sheet(tracking.from_row,
                                                                   self.base_spreadsheet_id,
                                                                   "Trackings")
    existing_tracking_numbers = set(
        [existing_tracking.tracking_number for existing_tracking in existing_trackings])
    new_trackings = [t for t in trackings if t.tracking_number not in existing_tracking_numbers]
    all_trackings = existing_trackings + new_trackings
    self.upload_all_trackings(all_trackings)

  def upload_all_trackings(self, trackings: List[tracking.Tracking]) -> None:
    six_months_ago = (date.today() - timedelta(weeks=26)).strftime("%Y-%m-%d")
    recent_trackings = [t for t in trackings if t.ship_date > six_months_ago]
    self.objects_to_sheet.upload_to_sheet(recent_trackings, self.base_spreadsheet_id, "Trackings")
