import clusters
import sheets_service
from functools import cmp_to_key
from objects_to_sheet import ObjectsToSheet


def total_tracked(cluster):
  return cluster.tracked_cost + cluster.adjustment


def compare(cluster_one, cluster_two):
  diff_one = total_tracked(cluster_one) - cluster_one.expected_cost
  diff_two = total_tracked(cluster_two) - cluster_two.expected_cost

  # If both negative, return the diff. If only one is negative, that one should
  # come first. If both are nonnegative, use the group
  if diff_one < 0 and diff_two < 0:
    return diff_one - diff_two
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
    below_cost_clusters = [
        cluster for cluster in all_clusters
        if (cluster.tracked_cost + cluster.adjustment) < cluster.expected_cost
    ]
    self.objects_to_sheet.upload_to_sheet(all_clusters, base_sheet_id,
                                          "Clusters")

  def fill_adjustments(self, all_clusters, base_sheet_id):
    print("Filling in cost adjustments if applicable")
    downloaded_clusters = self.objects_to_sheet.download_from_sheet(
        clusters.from_row, base_sheet_id, "Clusters")
    for downloaded_cluster in downloaded_clusters:
      if downloaded_cluster.adjustment:
        for cluster in all_clusters:
          if cluster.trackings.intersection(downloaded_cluster.trackings):
            cluster.adjustment += downloaded_cluster.adjustment
            break
