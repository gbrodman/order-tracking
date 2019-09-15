import pickle
import os.path
from objects_to_drive import ObjectsToDrive
from typing import Any, TypeVar

_T0 = TypeVar('_T0')

OUTPUT_FOLDER = "output"
TRACKINGS_FILENAME = "trackings.pickle"
TRACKINGS_FILE = OUTPUT_FOLDER + "/" + TRACKINGS_FILENAME


class TrackingOutput:

  def save_trackings(self, config, trackings) -> None:
    old_trackings = self.get_existing_trackings(config)
    merged_trackings = self.merge_trackings(old_trackings, trackings)
    self._write_merged(config, merged_trackings)

  def _write_merged(self, config, merged_trackings) -> None:
    if not os.path.exists(OUTPUT_FOLDER):
      os.mkdir(OUTPUT_FOLDER)

    with open(TRACKINGS_FILE, 'wb') as output:
      pickle.dump(merged_trackings, output)

    if 'driveFolder' in config:
      objects_to_drive = ObjectsToDrive()
      objects_to_drive.save(config['driveFolder'], TRACKINGS_FILENAME,
                            TRACKINGS_FILE)

  # Adds each Tracking object to the appropriate group
  # if there isn't already an entry for that tracking number
  def merge_trackings(self, old_trackings: _T0, trackings) -> _T0:
    for group, group_trackings in trackings.items():
      if group in old_trackings:
        old_group_trackings = old_trackings[group]
        old_tracking_numbers = set(
            [ogt.tracking_number for ogt in old_group_trackings])
        for new_group_tracking in group_trackings:
          if new_group_tracking.tracking_number not in old_tracking_numbers:
            old_group_trackings.append(new_group_tracking)
        old_trackings[group] = old_group_trackings
      else:
        old_trackings[group] = group_trackings
    return old_trackings

  def get_existing_trackings(self, config) -> Any:
    if 'driveFolder' in config:
      objects_to_drive = ObjectsToDrive()
      from_drive = objects_to_drive.load(config['driveFolder'],
                                         TRACKINGS_FILENAME)
      if from_drive:
        return from_drive

    print(
        "Drive folder ID not present or we couldn't load from drive. Loading from local"
    )
    if not os.path.exists(TRACKINGS_FILE):
      return {}

    with open(TRACKINGS_FILE, 'rb') as tracking_file_stream:
      return pickle.load(tracking_file_stream)

  def clear(self) -> None:
    # self.write_merged([])
    pass
