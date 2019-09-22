from lib import clusters
from functools import cmp_to_key
from lib.objects_to_sheet import ObjectsToSheet
from typing import Any, TypeVar

_T = TypeVar('_T')


def total_diff(cluster) -> Any:
  if cluster.manual_override:
    return 0
  return cluster.tracked_cost + cluster.adjustment - cluster.expected_cost


def compare(cluster_one, cluster_two) -> int:
  diff_one = total_diff(cluster_one)
  diff_two = total_diff(cluster_two)

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


def has_formatting(service, base_sheet_id, ranges):
  response = service.spreadsheets().get(
      spreadsheetId=base_sheet_id, ranges=ranges).execute()
  return "conditionalFormats" in str(response)


def clear_formatting(service, base_sheet_id, tab_id, tab_title):
  while has_formatting(service, base_sheet_id, [tab_title]):
    body = {
        "requests": [{
            "deleteConditionalFormatRule": {
                "sheetId": int(tab_id),
                "index": 0
            }
        }]
    }
    service.spreadsheets().batchUpdate(
        spreadsheetId=base_sheet_id, body=body).execute()


def get_conditional_formatting_body(service, base_sheet_id, tab_title,
                                    num_objects):
  response = service.spreadsheets().get(
      spreadsheetId=base_sheet_id, ranges=[tab_title]).execute()
  tab = [
      sheet for sheet in response['sheets']
      if sheet['properties']['title'] == tab_title
  ][0]
  tab_id = tab['properties']['sheetId']
  clear_formatting(service, base_sheet_id, tab_id, "Reconciliation")

  checkbox_range = {
      "sheetId": int(tab_id),
      "startRowIndex": 1,
      "endRowIndex": num_objects + 1,
      "startColumnIndex": 9,
      "endColumnIndex": 10
  }
  total_diff_range = {
      "sheetId": int(tab_id),
      "startRowIndex": 1,
      "endRowIndex": num_objects + 1,
      "startColumnIndex": 10,
      "endColumnIndex": 11
  }
  requests = [{
      "setDataValidation": {
          "range": checkbox_range,
          "rule": {
              "condition": {
                  'type': 'BOOLEAN'
              }
          }
      }
  }, {
      "addConditionalFormatRule": {
          "index": 0,
          "rule": {
              "ranges": [total_diff_range],
              "booleanRule": {
                  "condition": {
                      "type":
                          "CUSTOM_FORMULA",
                      "values": [{
                          'userEnteredValue':
                              '=OR((I2:I)+(D2:D)=C2:C, J2:J= TRUE)'
                      }]
                  },
                  "format": {
                      'backgroundColor': {
                          'red': 0.7176471,
                          'green': 0.88235295,
                          'blue': 0.8039216
                      }
                  }
              }
          }
      }
  }, {
      "addConditionalFormatRule": {
          "index": 1,
          "rule": {
              "ranges": [total_diff_range],
              "booleanRule": {
                  "condition": {
                      "type": "CUSTOM_FORMULA",
                      "values": [{
                          'userEnteredValue': '=(I2:I)+(D2:D)>C2:C'
                      }]
                  },
                  "format": {
                      'backgroundColor': {
                          'red': 0.9882353,
                          'green': 0.9098039,
                          'blue': 0.69803923
                      }
                  }
              }
          }
      }
  }, {
      "addConditionalFormatRule": {
          "index": 2,
          "rule": {
              "ranges": [total_diff_range],
              "booleanRule": {
                  "condition": {
                      "type": "CUSTOM_FORMULA",
                      "values": [{
                          'userEnteredValue': '=(I2:I)+(D2:D)<C2:C'
                      }]
                  },
                  "format": {
                      'backgroundColor': {
                          'red': 0.95686275,
                          'green': 0.78039217,
                          'blue': 0.7647059
                      }
                  }
              }
          }
      }
  }]
  return {"requests": requests}


class ReconciliationUploader:

  def __init__(self, config) -> None:
    self.config = config
    self.objects_to_sheet = ObjectsToSheet()

  def download_upload_clusters(self, all_clusters) -> None:
    base_sheet_id = self.config['reconciliation']['baseSpreadsheetId']
    self.fill_adjustments(all_clusters, base_sheet_id)

    all_clusters.sort(key=cmp_to_key(compare))
    self.objects_to_sheet.upload_to_sheet(all_clusters, base_sheet_id,
                                          "Reconciliation",
                                          get_conditional_formatting_body)

  def fill_adjustments(self, all_clusters, base_sheet_id) -> None:
    print("Filling in cost adjustments if applicable")
    downloaded_clusters = self.objects_to_sheet.download_from_sheet(
        clusters.from_row, base_sheet_id, "Reconciliation")

    for cluster in all_clusters:
      candidate_downloads = self.find_candidate_downloads(
          cluster, downloaded_clusters)
      cluster.adjustment = sum(
          [candidate.adjustment for candidate in candidate_downloads])
      cluster.notes = ", ".join(
          [candidate.notes for candidate in candidate_downloads])
      if candidate_downloads:
        cluster.manual_override = all(
            [candidate.manual_override for candidate in candidate_downloads])

  def find_candidate_downloads(self, cluster, downloaded_clusters) -> list:
    result = []
    for downloaded_cluster in downloaded_clusters:
      if downloaded_cluster.trackings.intersection(cluster.trackings):
        result.append(downloaded_cluster)
    return result