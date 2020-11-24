from lib.object_retriever import ObjectRetriever
from typing import Dict, Tuple

NON_PORTAL_TRACKINGS_FILENAME = "non_portal_trackings.pickle"
NON_PORTAL_POS_FILENAME = "non_portal_pos.pickle"


class NonPortalReimbursements:

  def __init__(self, config):
    self.retriever = ObjectRetriever(config)
    self.trackings_to_costs: Dict[Tuple[str],
                                  Tuple[str,
                                        float]] = self.retriever.load(NON_PORTAL_TRACKINGS_FILENAME)
    self.po_to_cost: Dict[str, float] = self.retriever.load(NON_PORTAL_POS_FILENAME)

  def flush(self):
    self.retriever.flush(self.trackings_to_costs, NON_PORTAL_TRACKINGS_FILENAME)
    self.retriever.flush(self.po_to_cost, NON_PORTAL_POS_FILENAME)
