from functools import cmp_to_key
from typing import List, Any, Set

from lib.group_site_manager import TrackingInfoDict
from lib.objects_to_sheet import ObjectsToSheet
from lib.tracking import convert_int_to_date


class UnknownTracking:

  def __init__(self, tracking_number, date, group, amount, manually_verified):
    self.tracking_number = tracking_number
    self.date = date
    self.group = group
    self.amount = amount
    self.manually_verified = manually_verified

  def to_row(self) -> List[Any]:
    return [self.tracking_number, self.date, self.group, self.amount, self.manually_verified]

  def get_header(self) -> List[str]:
    return ['Tracking Number', 'Date', 'Group', 'Amount', 'Manually Verified']


def _unknown_tracking_from_row(header, row):
  tracking_number = str(row[header.index('Tracking Number')])
  date = row[header.index("Date")]
  if isinstance(date, int):
    date = convert_int_to_date(date)
  group = row[header.index('Group')]
  amount = float(row[header.index('Amount')])
  manually_verified = row[header.index('Manually Verified')]
  return UnknownTracking(tracking_number, date, group, amount, manually_verified)


def compare(one: UnknownTracking, two: UnknownTracking) -> int:
  # manually verified ones come last
  if two.manually_verified and not one.manually_verified:
    return -1
  elif one.manually_verified and not two.manually_verified:
    return 1
  # next, dates -- most recent coming first
  if one.date > two.date:
    return -1
  elif two.date > one.date:
    return 1
  # next, groups
  if one.group > two.group:
    return 1
  elif two.group > one.group:
    return -1
  return 0


def _get_unknown_trackings_from_sheet(sheet_id) -> List[UnknownTracking]:
  objects_to_sheet = ObjectsToSheet()
  return objects_to_sheet.download_from_sheet(_unknown_tracking_from_row, sheet_id,
                                              'Unknown Trackings')


def upload_unknown_trackings(sheet_id: str, known_trackings: Set[str],
                             trackings_from_groups: TrackingInfoDict) -> None:
  print("Uploading list of unknown trackings")
  unknown_trackings = []
  for tracking_tuple in trackings_from_groups.keys():
    for tracking in tracking_tuple:
      if tracking not in known_trackings:
        group, amount, date = trackings_from_groups[tracking_tuple]
        unknown_trackings.append(UnknownTracking(tracking, date, group, amount, False))

  unknown_trackings_by_num = {u.tracking_number: u for u in unknown_trackings}

  for previous_unknown_tracking in _get_unknown_trackings_from_sheet(sheet_id):
    if previous_unknown_tracking.manually_verified and previous_unknown_tracking.tracking_number in unknown_trackings_by_num:
      unknown_trackings_by_num[previous_unknown_tracking.tracking_number].manually_verified = True

  unknown_trackings.sort(key=cmp_to_key(compare))
  ObjectsToSheet().upload_to_sheet(unknown_trackings, sheet_id, 'Unknown Trackings')
