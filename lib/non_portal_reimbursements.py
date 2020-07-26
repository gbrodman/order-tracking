import pickle
import os.path

from lib.objects_to_drive import ObjectsToDrive
from typing import Dict, Tuple

OUTPUT_FOLDER = "output"
NON_PORTAL_TRACKINGS_FILENAME = "non_portal_trackings.pickle"
NON_PORTAL_POS_FILENAME = "non_portal_pos.pickle"


class NonPortalReimbursements:
  """
  A class that stores and retrieves non-portal reimbursements. Used for groups that don't have web portals.
  """

  def __init__(self, config) -> None:
    self.config = config
    self.trackings_to_costs: Dict[Tuple[str],
                                  Tuple[str, float]] = self._load(NON_PORTAL_TRACKINGS_FILENAME)
    self.po_to_cost: Dict[str, float] = self._load(NON_PORTAL_POS_FILENAME)

  def flush(self) -> None:
    self._flush(self.trackings_to_costs, NON_PORTAL_TRACKINGS_FILENAME)
    self._flush(self.po_to_cost, NON_PORTAL_POS_FILENAME)

  def _flush(self, obj, filename):
    if not os.path.exists(OUTPUT_FOLDER):
      os.mkdir(OUTPUT_FOLDER)

    local_file = OUTPUT_FOLDER + "/" + filename
    with open(local_file, 'wb') as stream:
      pickle.dump(obj, stream)

    objects_to_drive = ObjectsToDrive()
    objects_to_drive.save(self.config, filename, local_file)

  def _load(self, filename):
    objects_to_drive = ObjectsToDrive()
    from_drive = objects_to_drive.load(self.config, filename)
    if from_drive:
      return from_drive

    local_file = OUTPUT_FOLDER + "/" + filename
    if not os.path.exists(local_file):
      return {}

    with open(local_file, 'rb') as stream:
      return pickle.load(stream)
