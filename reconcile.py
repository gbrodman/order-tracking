#!/usr/bin/env python3

import argparse
from typing import Dict, Tuple, List

from lib import clusters, util
from tqdm import tqdm
from lib.cancelled_items_retriever import CancelledItemsRetriever
from lib.clusters import Cluster
from lib.config import open_config
from lib.et import et
from lib.order_info import OrderInfoRetriever
from lib.group_site_manager import GroupSiteManager, TrackingInfoDict, PoCostDict, ReconResult
from lib.driver_creator import DriverCreator
from lib.portal_reimbursements import NonPortalReimbursements
from lib.reconciliation_uploader import ReconciliationUploader
from lib.tracking_output import TrackingOutput
from lib.unknown_trackings import upload_unknown_trackings


def fill_billed_costs(tqdm_msg: str, all_clusters: List[Cluster],
                      order_info_retriever: OrderInfoRetriever, fetch_from_email: bool):
  total_orders = sum([len(cluster.orders) for cluster in all_clusters])
  with tqdm(desc=tqdm_msg, unit='order', total=total_orders) as pbar:
    for cluster in all_clusters:
      cluster.expected_cost = 0.0
      cluster.email_ids = set()
      for order_id in cluster.orders:
        try:
          order_info = order_info_retriever.get_order_info(order_id, fetch_from_email)
          cluster.expected_cost += order_info.cost
          if order_info.email_id:
            # Only add the email ID if it's present; don't add Nones!
            cluster.email_ids.add(order_info.email_id)
        except Exception as e:
          tqdm.write(
              f"Exception when getting order info for {order_id}. Please check the oldest email associated with that order. Skipping..."
          )
          tqdm.write(str(e))
          tqdm.write(util.get_traceback_lines())
        pbar.update()


def apply_non_portal_reimbursements(config, groups, trackings_to_costs_map: TrackingInfoDict,
                                    po_to_cost_map: PoCostDict) -> None:
  non_portal_reimbursements = NonPortalReimbursements(config)
  duplicate_tracking_tuples = set(non_portal_reimbursements.trackings_to_costs.keys()).intersection(
      trackings_to_costs_map.keys())
  if duplicate_tracking_tuples:
    for duplicate in duplicate_tracking_tuples:
      print(
          f'Tracking {duplicate} in non-portal reimbursements also group {trackings_to_costs_map[duplicate][0]}'
      )
    raise Exception('Non-reimbursed trackings should not be duplicated in a portal')

  duplicate_pos = set(non_portal_reimbursements.po_to_cost.keys()).intersection(
      po_to_cost_map.keys())
  if duplicate_pos:
    for duplicate_po in duplicate_pos:
      print(f'PO {duplicate_po} included in non-portal reimbursements but also found in a portal')
    raise Exception('Non-reimbursed POs should not be duplicated in a portal')

  filtered_non_portal_trackings = {
      key: (value[0], value[1], '')
      for (key, value) in non_portal_reimbursements.trackings_to_costs.items()
      if value[0] in groups
  }
  if len(non_portal_reimbursements.trackings_to_costs) != len(filtered_non_portal_trackings):
    print(f"Potential error! There were {len(non_portal_reimbursements.trackings_to_costs)} "
          f"non-portal reimbursements, but only {len(filtered_non_portal_trackings)} matched "
          f"group names specified in config file.")
  print(f"Importing {len(filtered_non_portal_trackings)} non-portal reimbursements.")
  trackings_to_costs_map.update(filtered_non_portal_trackings)
  po_to_cost_map.update(non_portal_reimbursements.po_to_cost)


def get_new_tracking_pos_costs_maps(config, group_site_manager: GroupSiteManager,
                                    args) -> ReconResult:
  print("Loading tracked costs. This can take several minutes.")
  if args.groups:
    print("Only reconciling groups %s" % ",".join(args.groups))
    groups = args.groups
  else:
    groups = config['groups'].keys()

  trackings_to_info: TrackingInfoDict = {}
  po_to_cost: PoCostDict = {}
  for group in groups:
    group_trackings_to_info, group_po_to_cost = group_site_manager.get_new_tracking_pos_costs_maps_with_retry(
        group)
    # Update the maps
    trackings_to_info.update(group_trackings_to_info)
    po_to_cost.update(group_po_to_cost)

  apply_non_portal_reimbursements(config, groups, trackings_to_info, po_to_cost)
  return trackings_to_info, po_to_cost


def map_clusters_by_tracking(all_clusters):
  result = {}
  for cluster in all_clusters:
    for tracking in cluster.trackings:
      result[tracking] = cluster
  return result


def merge_by_trackings_tuples(clusters_by_tracking, trackings_to_cost, all_clusters):
  for trackings_tuple, cost in trackings_to_cost.items():
    if len(trackings_tuple) == 1:
      continue

    cluster_list = [
        clusters_by_tracking[tracking]
        for tracking in trackings_tuple
        if tracking in clusters_by_tracking
    ]

    if not cluster_list:
      continue

    # Merge all candidate clusters into the first cluster (if they're not already part of it)
    # then set all trackings to have the first cluster as their value
    first_cluster = cluster_list[0]
    for other_cluster in cluster_list[1:]:
      if not (other_cluster.trackings.issubset(first_cluster.trackings) and
              other_cluster.orders.issubset(first_cluster.orders)):
        if other_cluster in all_clusters:
          all_clusters.remove(other_cluster)
        first_cluster.merge_with(other_cluster)
    for tracking in trackings_tuple:
      clusters_by_tracking[tracking] = first_cluster


def fill_costs_new(clusters_by_tracking, trackings_to_cost: TrackingInfoDict,
                   po_to_cost: PoCostDict, args):
  for cluster in clusters_by_tracking.values():
    # Reset the cluster if it's included in the groups
    if args.groups and cluster.group not in args.groups:
      continue
    cluster.non_reimbursed_trackings = set(cluster.trackings)
    cluster.tracked_cost = 0

  # We've already merged by tracking tuple (if multiple trackings are counted as the same price)
  # so only use the first tracking in each tuple
  for trackings_tuple, (group, cost, date) in trackings_to_cost.items():
    if not trackings_tuple:
      continue
    first_tracking: str = trackings_tuple[0]
    if first_tracking in clusters_by_tracking:
      cluster = clusters_by_tracking[first_tracking]
      cluster.tracked_cost += cost
      for tracking in trackings_tuple:
        if tracking in cluster.non_reimbursed_trackings:
          cluster.non_reimbursed_trackings.remove(tracking)

  # Next, manual PO fixes
  for cluster in clusters_by_tracking.values():
    pos = cluster.purchase_orders
    if pos:
      for po in pos:
        cluster.tracked_cost += float(po_to_cost.get(po, 0.0))


def fill_cancellations(all_clusters, config):
  retriever = CancelledItemsRetriever(config)
  cancellations_by_order = retriever.get_cancelled_items()

  for cluster in all_clusters:
    cluster.cancelled_items = []
    for order in cluster.orders:
      if order in cancellations_by_order:
        cluster.cancelled_items += cancellations_by_order[order]


def reconcile_new(config, args):
  reconciliation_uploader = ReconciliationUploader(config)

  tracking_output = TrackingOutput(config)
  trackings = tracking_output.get_existing_trackings()
  reconcilable_trackings = [t for t in trackings if t.reconcile]
  # start from scratch
  all_clusters = []
  clusters.update_clusters(all_clusters, reconcilable_trackings)

  order_info_retriever = OrderInfoRetriever(config)
  fill_billed_costs('Fetching order costs', all_clusters, order_info_retriever, True)
  all_clusters = clusters.merge_orders(all_clusters)
  fill_billed_costs('Filling merged order costs', all_clusters, order_info_retriever, False)

  # add manual PO entries (and only manual ones)
  reconciliation_uploader.override_pos_and_costs(all_clusters)

  driver_creator = DriverCreator()
  group_site_manager = GroupSiteManager(config, driver_creator)

  trackings_to_info, po_to_cost = get_new_tracking_pos_costs_maps(config, group_site_manager, args)

  clusters_by_tracking = map_clusters_by_tracking(all_clusters)
  merge_by_trackings_tuples(clusters_by_tracking, trackings_to_info, all_clusters)

  fill_costs_new(clusters_by_tracking, trackings_to_info, po_to_cost, args)

  fill_cancellations(all_clusters, config)
  et(config, all_clusters)
  sheet_id = config['reconciliation']['baseSpreadsheetId']
  if args.groups:
    print("Skipping unknown-tracking upload due to the --groups argument")
  else:
    upload_unknown_trackings(sheet_id, set(clusters_by_tracking.keys()), trackings_to_info)
  reconciliation_uploader.download_upload_clusters_new(all_clusters)


def main():
  parser = argparse.ArgumentParser(description='Reconciliation script')
  parser.add_argument("--groups", nargs="*")
  args, _ = parser.parse_known_args()
  config = open_config()

  print("Reconciling ...")
  reconcile_new(config, args)


if __name__ == "__main__":
  main()
