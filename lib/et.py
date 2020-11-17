import datetime
from typing import List

from lib.clusters import Cluster
from lib.objects_to_sheet import ObjectsToSheet
from lib.order_info import MISSING_COST_SENTINEL

SHEET_ID = '1T-X_HxJhfiG5MXqzk826UX_OF7NHdL2Nn-O2u_IPZaQ'
TAB_TITLE = 'Totals'
THREE_MONTHS_AGO = (datetime.date.today() - datetime.timedelta(weeks=13)).strftime("%Y-%m-%d")


class Total:

  def __init__(self, email, total):
    self.email = email
    self.total = total

  def to_row(self):
    return [self.email, self.total]

  def get_header(self):
    return ['Email', 'Total']


def from_row(header, row):
  email = row[header.index('Email')]
  total = float(row[header.index('Total')])
  return Total(email, total)


def should_include(cluster: Cluster):
  if cluster.expected_cost >= MISSING_COST_SENTINEL - 1:
    return False
  if not cluster.last_ship_date:
    return False
  if cluster.last_ship_date.lower() == 'n/a':
    return False
  return cluster.last_ship_date >= THREE_MONTHS_AGO


def compute_total(all_clusters: List[Cluster]) -> float:
  total = 0
  for cluster in all_clusters:
    if should_include(cluster):
      total += cluster.expected_cost
  return total


def et(config, all_clusters: List[Cluster]) -> None:
  email = config['email']['username']
  objects_to_sheet = ObjectsToSheet()
  existing_totals = objects_to_sheet.download_from_sheet(from_row, SHEET_ID, TAB_TITLE)
  existing_totals = [t for t in existing_totals if t.email != email]
  existing_totals.append(Total(email, compute_total(all_clusters)))
  objects_to_sheet.upload_to_sheet(existing_totals, SHEET_ID, TAB_TITLE)
