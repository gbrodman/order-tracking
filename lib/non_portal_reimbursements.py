import pickle
import os.path

from lib.objects_to_drive import ObjectsToDrive
from typing import Dict, Tuple

OUTPUT_FOLDER = "output"
NON_PORTAL_REIMBURSEMENTS_FILENAME = "non_portal_reimbursements.pickle"
NON_PORTAL_REIMBURSEMENTS_FILE = OUTPUT_FOLDER + "/" + NON_PORTAL_REIMBURSEMENTS_FILENAME


class NonPortalReimbursements:

  def __init__(self, trackings_to_costs: Dict[Tuple[str], Tuple[str, float]], po_to_cost: Dict[str, float]):
    # Dict from (trackings) -> (group, reimbursed-cost)
    self.trackings_to_costs = trackings_to_costs
    # Simple dict from po -> cost
    self.po_to_cost = po_to_cost


class NonPortalReimbursementsRetriever:
  """
  A class that stores and retrieves non-portal reimbursements. Used for groups that don't have web portals.
  """

  def __init__(self, config) -> None:
    self.config = config
    self.non_portal_reimbursements = self.load_non_portal_reimbursements()

  def flush(self) -> None:
    if not os.path.exists(OUTPUT_FOLDER):
      os.mkdir(OUTPUT_FOLDER)

    with open(NON_PORTAL_REIMBURSEMENTS_FILE, 'wb') as stream:
      pickle.dump(self.non_portal_reimbursements, stream)

    objects_to_drive = ObjectsToDrive()
    objects_to_drive.save(self.config, NON_PORTAL_REIMBURSEMENTS_FILENAME,
                          NON_PORTAL_REIMBURSEMENTS_FILE)

  def load_non_portal_reimbursements(self) -> NonPortalReimbursements:
    objects_to_drive = ObjectsToDrive()
    from_drive = objects_to_drive.load(self.config, NON_PORTAL_REIMBURSEMENTS_FILENAME)
    if from_drive:
      return from_drive

    if not os.path.exists(NON_PORTAL_REIMBURSEMENTS_FILE):
      return NonPortalReimbursements({}, {})

    with open(NON_PORTAL_REIMBURSEMENTS_FILE, 'rb') as stream:
      return pickle.load(stream)
