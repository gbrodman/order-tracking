import sheets_service
from objects_to_sheet import ObjectsToSheet


class ReconciliationUploader:

  def __init__(self, config):
    self.config = config
    self.service = sheets_service.create()
    self.objects_to_sheet = ObjectsToSheet()

  def upload_clusters(self, clusters):
    clusters_by_group = self.partition_by_group(clusters)
    base_sheet_id = self.config['reconciliation']['baseSpreadsheetId']
    group_sheet_ids = self.config['reconciliation']['sheetIds']

    for group, clusters in clusters_by_group.items():
      if group not in group_sheet_ids.keys():
        continue
      group_sheet_id = group_sheet_ids[group]

      below_cost_clusters = [
          cluster for cluster in clusters
          if cluster.tracked_cost < cluster.expected_cost
      ]
      self.objects_to_sheet.upload_to_sheet(clusters, base_sheet_id,
                                            group_sheet_id)
      self.objects_to_sheet.upload_to_sheet(below_cost_clusters, base_sheet_id,
                                            group_sheet_id + "-BELOW")

  def partition_by_group(self, clusters):
    result = {}
    for cluster in clusters:
      if cluster.group not in result:
        result[cluster.group] = []
      result[cluster.group].append(cluster)
    return result
