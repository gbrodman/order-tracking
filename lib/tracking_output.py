import collections
from typing import List, Optional

from lib.object_retriever import ObjectRetriever
from lib.tracking import Tracking

TRACKINGS_FILENAME = "trackings.pickle"


class TrackingOutput:

  def __init__(self, config) -> None:
    self.retriever = ObjectRetriever(config)

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

    self.retriever.flush(groups_dict, TRACKINGS_FILENAME)

  # Adds each Tracking object to the appropriate group
  # if there isn't already an entry for that tracking number
  def merge_trackings(self, old_trackings: List[Tracking], trackings: List[Tracking],
                      overwrite: bool) -> List[Tracking]:
    new_tracking_dict = {t.tracking_number: t for t in old_trackings}
    for tracking in trackings:
      if tracking.tracking_number not in new_tracking_dict or overwrite:
        new_tracking_dict[tracking.tracking_number] = tracking
    return list(new_tracking_dict.values())

  def get_existing_trackings(self) -> List[Tracking]:
    trackings_dict = self.retriever.load(TRACKINGS_FILENAME)
    return self._convert_to_list(trackings_dict)

  def _convert_to_list(self, trackings_dict):
    result = []
    for trackings in trackings_dict.values():
      result.extend(trackings)
    for tracking in result:
      tracking.tracking_number = tracking.tracking_number.upper()
    return result
