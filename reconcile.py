#!/usr/bin/env python3

import argparse
import lib.donations
from lib import clusters
import sys
from tqdm import tqdm
import yaml
from lib.order_info import OrderInfo, OrderInfoRetriever
from lib.group_site_manager import GroupSiteManager
from lib.driver_creator import DriverCreator
from lib.reconciliation_uploader import ReconciliationUploader
from lib.tracking_output import TrackingOutput
from lib.tracking_uploader import TrackingUploader

CONFIG_FILE = "config.yml"


def get_tracking_pos_costs_maps(config, group_site_manager, args):
  print("Loading tracked costs. This will take several minutes.")
  if args.groups:
    print("Only reconciling groups %s" % ",".join(args.groups))
    groups = args.groups
  else:
    groups = config['groups'].keys()

  tracking_to_po_map = {}
  po_to_cost_map = {}
  for group in groups:
    group_tracking_to_po, group_po_to_cost = group_site_manager.get_tracking_pos_costs_maps_with_retry(
        group)
    tracking_to_po_map.update(group_tracking_to_po)
    po_to_cost_map.update(group_po_to_cost)

  return (tracking_to_po_map, po_to_cost_map)


def fill_purchase_orders(all_clusters, tracking_to_po, args):
  print("Filling purchase orders")

  for cluster in all_clusters:
    if args.groups and cluster.group not in args.groups:
      continue

    cluster.non_reimbursed_trackings = set(cluster.trackings)
    for tracking in cluster.trackings:
      if tracking in tracking_to_po:
        cluster.purchase_orders.add(tracking_to_po[tracking])
        cluster.non_reimbursed_trackings.remove(tracking)


def fill_costs_by_po(all_clusters, po_to_cost, args, group_site_manager):
  tracked_groups = group_site_manager.get_tracked_groups()
  for cluster in all_clusters:
    if cluster.purchase_orders and (
        not args.groups or
        cluster.group in args.groups) and cluster.group in tracked_groups:
      cluster.tracked_cost = sum(
          [po_to_cost.get(po, 0.0) for po in cluster.purchase_orders])


def fill_order_info(all_clusters, config):
  order_info_retriever = OrderInfoRetriever(config)
  total_orders = sum([len(cluster.orders) for cluster in all_clusters])
  with tqdm(
      desc='Fetching order costs', unit='order', total=total_orders) as pbar:
    for cluster in all_clusters:
      cluster.expected_cost = 0.0
      cluster.email_ids = set()
      for order_id in cluster.orders:
        try:
          order_info = order_info_retriever.get_order_info(order_id)
          # Only add the email ID if it's present; don't add Nones!
          if order_info.email_id:
            cluster.email_ids.add(order_info.email_id)
          cluster.expected_cost += order_info.cost
        except Exception as e:
          tqdm.write(
              f"Exception when getting order info for {order_id}. Please check the oldest email associated with that order. Skipping..."
          )
          tqdm.write(str(e))
        pbar.update()


def clusterify(config):
  tracking_output = TrackingOutput(config)
  print("Getting all tracking objects")
  trackings = tracking_output.get_existing_trackings()
  reconcilable_trackings = [t for t in trackings if t.reconcile]

  print("Converting to Cluster objects")
  all_clusters = clusters.get_existing_clusters(config)
  clusters.update_clusters(all_clusters, reconcilable_trackings)

  print("Filling out order info and writing results to disk")
  fill_order_info(all_clusters, config)
  clusters.write_clusters(config, all_clusters)


def get_new_tracking_pos_costs_maps(config, group_site_manager, args):
  print("Loading tracked costs. This will take several minutes.")
  if args.groups:
    print("Only reconciling groups %s" % ",".join(args.groups))
    groups = args.groups
  else:
    groups = config['groups'].keys()

  trackings_to_costs_map = {}
  po_to_cost_map = {}
  for group in groups:
    group_trackings_to_po, group_po_to_cost = group_site_manager.get_new_tracking_pos_costs_maps_with_retry(
        group)
    trackings_to_costs_map.update(group_trackings_to_po)
    po_to_cost_map.update(group_po_to_cost)

  return (trackings_to_costs_map, po_to_cost_map)


def map_clusters_by_tracking(all_clusters):
  result = {}
  for cluster in all_clusters:
    for tracking in cluster.trackings:
      result[tracking] = cluster
  return result


def merge_by_trackings_tuples(clusters_by_tracking, trackings_to_cost):
  for trackings_tuple, cost in trackings_to_cost.items():
    if len(trackings_tuple) == 1:
      continue

    cluster_list = [
        clusters_by_tracking[tracking] for tracking in trackings_tuple
    ]
    # Merge all candidate clusters into the first cluster (if they're not already part of it)
    # then set all trackings to have the first cluster as their value
    first_cluster = cluster_list[0]
    for other_cluster in cluster_list[1:]:
      if not (other_cluster.trackings.issubset(first_cluster.trackings) and
              other_cluster.orders.issubset(first_cluster.orders)):
        first_cluster.merge_with(other_cluster)
    for tracking in trackings_tuple:
      clusters_by_tracking[tracking] = first_cluster


def fill_costs_new(clusters_by_tracking, trackings_to_cost, po_to_cost, args):
  for cluster in clusters_by_tracking.values():
    # Reset the cluster if it's included in the groups
    if args.groups and cluster.group not in args.groups:
      continue
    cluster.non_reimbursed_trackings = set(cluster.trackings)
    cluster.tracked_cost = 0

  # We've already merged by tracking tuple (if multiple trackings are counted as the same price)
  # so only use the first tracking in each tuple
  for trackings_tuple, cost in trackings_to_cost.items():
    first_tracking = trackings_tuple[0]
    if first_tracking in clusters_by_tracking:
      cluster = clusters_by_tracking[first_tracking]
      cluster.tracked_cost += cost
      for tracking in trackings_tuple:
        cluster.non_reimbursed_trackings.remove(tracking)

  # Next, manual PO fixes
  for cluster in clusters_by_tracking.values():
    pos = cluster.purchase_orders
    if pos:
      for po in pos:
        cluster.tracked_cost += float(po_to_cost.get(po, 0.0))


def reconcile_new(config, args):
  print("New reconciliation!")
  reconciliation_uploader = ReconciliationUploader(config)

  tracking_output = TrackingOutput(config)
  trackings = tracking_output.get_existing_trackings()
  reconcilable_trackings = [t for t in trackings if t.reconcile]
  # start from scratch
  all_clusters = []
  clusters.update_clusters(all_clusters, reconcilable_trackings)

  fill_order_info(all_clusters, config)
  all_clusters = clusters.merge_orders(all_clusters)

  # add manual PO entries (and only manual ones)
  reconciliation_uploader.override_pos_and_costs(all_clusters)

  driver_creator = DriverCreator()
  group_site_manager = GroupSiteManager(config, driver_creator)

  trackings_to_cost, po_to_cost = get_new_tracking_pos_costs_maps(
      config, group_site_manager, args)
  clusters_by_tracking = map_clusters_by_tracking(all_clusters)
  merge_by_trackings_tuples(clusters_by_tracking, trackings_to_cost)

  fill_costs_new(clusters_by_tracking, trackings_to_cost, po_to_cost, args)
  reconciliation_uploader.download_upload_clusters_new(all_clusters)


def main():
  parser = argparse.ArgumentParser(description='Reconciliation script')
  parser.add_argument("--groups", nargs="*")
  args, _ = parser.parse_known_args()

  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)

  reconcile_new(config, args)

  clusterify(config)

  reconciliation_uploader = ReconciliationUploader(config)
  all_clusters = clusters.get_existing_clusters(config)
  reconciliation_uploader.override_pos(all_clusters)

  driver_creator = DriverCreator()
  group_site_manager = GroupSiteManager(config, driver_creator)
  tracking_to_po, po_to_cost = get_tracking_pos_costs_maps(
      config, group_site_manager, args)

  fill_purchase_orders(all_clusters, tracking_to_po, args)
  all_clusters = clusters.merge_orders(all_clusters)
  fill_costs_by_po(all_clusters, po_to_cost, args, group_site_manager)

  reconciliation_uploader.download_upload_clusters(all_clusters)
  clusters.write_clusters(config, all_clusters)


if __name__ == "__main__":
  main()
