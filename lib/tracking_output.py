import collections
import pickle
from typing import List, Optional
import os.path
from lib.objects_to_drive import ObjectsToDrive
from lib.tracking import Tracking

OUTPUT_FOLDER = "output"
TRACKINGS_FILENAME = "trackings.pickle"
TRACKINGS_FILE = OUTPUT_FOLDER + "/" + TRACKINGS_FILENAME


class TrackingOutput:

  def __init__(self, config) -> None:
    self.config = config


  def save_trackings(self, trackings, overwrite=False) -> None:
    old_trackings = self.get_existing_trackings()
    merged_trackings = self.merge_trackings(old_trackings, trackings, overwrite)
    self._write_merged(merged_trackings)


  def get_tracking(self, tracking_number) -> Optional[Tracking]:
    """Returns the tracking object with the given tracking number if it exists."""
    existing_trackings = self.get_existing_trackings()
    for tracking in existing_trackings:
      if tracking.tracking_number == tracking_number:
        return tracking
    return None


  def _write_merged(self, merged_trackings) -> None:
    groups_dict = collections.defaultdict(list)
    for tracking in merged_trackings:
      groups_dict[tracking.group].append(tracking)

    if not os.path.exists(OUTPUT_FOLDER):
      os.mkdir(OUTPUT_FOLDER)

    with open(TRACKINGS_FILE, 'wb') as output:
      pickle.dump(groups_dict, output)

    objects_to_drive = ObjectsToDrive()
    objects_to_drive.save(self.config, TRACKINGS_FILENAME, TRACKINGS_FILE)

  # Adds each Tracking object to the appropriate group
  # if there isn't already an entry for that tracking number
  def merge_trackings(self, old_trackings: List[Tracking], trackings: List[Tracking], overwrite: bool) -> List[Tracking]:
    new_tracking_dict = {t.tracking_number: t for t in old_trackings}
    for tracking in trackings:
      if not new_tracking_dict[tracking.tracking_number] or overwrite:
        new_tracking_dict[tracking.tracking_number] = tracking
    return list(new_tracking_dict.values())


  def get_existing_trackings(self) -> List[Tracking]:
    objects_to_drive = ObjectsToDrive()
    from_drive = objects_to_drive.load(self.config, TRACKINGS_FILENAME)
    if from_drive:
      return self._convert_to_list(from_drive)

    print(
        "Drive folder ID not present or we couldn't load from drive. Loading from local"
    )
    if not os.path.exists(TRACKINGS_FILE):
      return []

    with open(TRACKINGS_FILE, 'rb') as tracking_file_stream:
      trackings_dict = pickle.load(tracking_file_stream)
    return self._convert_to_list(trackings_dict)


  def _convert_to_list(self, trackings_dict):
    result = []
    for trackings in trackings_dict.values():
      result.extend(trackings)
    for tracking in result:
      tracking.tracking_number = tracking.tracking_number.upper()
    return result


  def clear(self) -> None:
    # self.write_merged([])
    pass
