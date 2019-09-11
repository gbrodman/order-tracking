import clusters
import sheets_service
from functools import cmp_to_key
from objects_to_sheet import ObjectsToSheet


def total_tracked(cluster):
  return cluster.tracked_cost + cluster.adjustment


def compare(cluster_one, cluster_two):
  diff_one = total_tracked(cluster_one) - cluster_one.expected_cost
  diff_two = total_tracked(cluster_two) - cluster_two.expected_cost

  # If both negative, return the ship date diff. If only one is
  # negative, that one should come first. If both are nonnegative, use the group
  if diff_one < 0 and diff_two < 0:
    if cluster_one.last_ship_date < cluster_two.last_ship_date:
      return -1
    elif cluster_one.last_ship_date == cluster_two.last_ship_date:
      return 0
    else:
      return 1
  elif diff_one < 0:
    return -1
  elif diff_two < 0:
    return 1
  elif cluster_one.group < cluster_two.group:
    return -1
  elif cluster_one.group == cluster_two.group:
    return 0
  else:
    return 1


class ReconciliationUploader:

  def __init__(self, config):
    self.config = config
    self.service = sheets_service.create()
    self.objects_to_sheet = ObjectsToSheet()

  def download_upload_clusters(self, all_clusters):
    base_sheet_id = self.config['reconciliation']['baseSpreadsheetId']
    self.fill_adjustments(all_clusters, base_sheet_id)

    all_clusters.sort(key=cmp_to_key(compare))
    self.objects_to_sheet.upload_to_sheet(all_clusters, base_sheet_id,
                                          "Clusters")

  def fill_adjustments(self, all_clusters, base_sheet_id):
    print("Filling in cost adjustments if applicable")
    downloaded_clusters = self.objects_to_sheet.download_from_sheet(
        clusters.from_row, base_sheet_id, "Clusters")

    for cluster in all_clusters:
      candidate_downloads = self.find_candidate_downloads(
          cluster, downloaded_clusters)
      cluster.adjustment = sum(
          [candidate.adjustment for candidate in candidate_downloads])

  def find_candidate_downloads(self, cluster, downloaded_clusters):
    result = []
    for downloaded_cluster in downloaded_clusters:
      if downloaded_cluster.trackings.intersection(cluster.trackings):
        result.append(downloaded_cluster)
    return result
