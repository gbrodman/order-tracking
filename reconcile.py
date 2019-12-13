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


def get_tracking_pos_costs_maps(config, driver_creator, args):
  print("Loading tracked costs. This will take several minutes.")
  group_site_manager = GroupSiteManager(config, driver_creator)

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


def fill_costs_by_po(all_clusters, po_to_cost, args):
  for cluster in all_clusters:
    if cluster.purchase_orders and (not args.groups or
                                    cluster.group in args.groups):
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
        order_info = order_info_retriever.get_order_info(order_id)
        # Only add the email ID if it's present; don't add Nones!
        if order_info.email_id:
          cluster.email_ids.add(order_info.email_id)
        cluster.expected_cost += order_info.cost
        pbar.update()


def clusterify(config):
  tracking_output = TrackingOutput(config)
  print("Getting all tracking objects")
  trackings = tracking_output.get_existing_trackings()

  print("Converting to Cluster objects")
  all_clusters = clusters.get_existing_clusters(config)
  clusters.update_clusters(all_clusters, trackings)

  print("Filling out order info and writing results to disk")
  fill_order_info(all_clusters, config)
  clusters.write_clusters(config, all_clusters)


def main():
  parser = argparse.ArgumentParser(description='Reconciliation script')
  parser.add_argument("--groups", nargs="*")
  args, _ = parser.parse_known_args()

  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)

  clusterify(config)

  reconciliation_uploader = ReconciliationUploader(config)
  all_clusters = clusters.get_existing_clusters(config)
  reconciliation_uploader.override_pos(all_clusters)

  driver_creator = DriverCreator()
  tracking_to_po, po_to_cost = get_tracking_pos_costs_maps(
      config, driver_creator, args)

  fill_purchase_orders(all_clusters, tracking_to_po, args)
  all_clusters = clusters.merge_orders(all_clusters)
  fill_costs_by_po(all_clusters, po_to_cost, args)

  reconciliation_uploader.download_upload_clusters(all_clusters)
  clusters.write_clusters(config, all_clusters)


if __name__ == "__main__":
  main()
