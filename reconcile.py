#!/usr/bin/env python3

import lib.donations
from lib import clusters
import yaml
import sys
from lib.expected_costs import ExpectedCosts
from lib.group_site_manager import GroupSiteManager
from lib.driver_creator import DriverCreator
from lib.reconciliation_uploader import ReconciliationUploader
from lib.tracking_output import TrackingOutput
from lib.tracking_uploader import TrackingUploader

CONFIG_FILE = "config.yml"


def get_tracking_pos_costs_maps(config, driver_creator):
  print("Loading tracked costs. This will take several minutes.")
  group_site_manager = GroupSiteManager(config, driver_creator)
  tracking_to_po_map = {}
  po_to_cost_map = {}

  for group in config['groups'].keys():
    group_tracking_to_po, group_po_to_cost = group_site_manager.get_tracking_pos_costs_maps_with_retry(
        group)
    tracking_to_po_map.update(group_tracking_to_po)
    po_to_cost_map.update(group_po_to_cost)

  return (tracking_to_po_map, po_to_cost_map)


def fill_purchase_orders(all_clusters, tracking_to_po):
  print("Filling purchase orders")

  for cluster in all_clusters:
    cluster.non_reimbursed_trackings = set(cluster.trackings)
    for tracking in cluster.trackings:
      if tracking in tracking_to_po:
        cluster.purchase_orders.add(tracking_to_po[tracking])
        cluster.non_reimbursed_trackings.remove(tracking)


def fill_costs_by_po(all_clusters, po_to_cost):
  for cluster in all_clusters:
    if cluster.purchase_orders:
      cluster.tracked_cost = sum(
          [po_to_cost.get(po, 0.0) for po in cluster.purchase_orders])


def fill_expected_costs(all_clusters, config):
  expected_costs = ExpectedCosts(config)
  for cluster in all_clusters:
    total_expected_cost = sum([
        expected_costs.get_expected_cost(order_id)
        for order_id in cluster.orders
    ])
    cluster.expected_cost = total_expected_cost


def clusterify(config):
  tracking_output = TrackingOutput()
  print("Getting all tracking objects")
  trackings = tracking_output.get_existing_trackings(config)

  print("Converting to Cluster objects")
  all_clusters = clusters.get_existing_clusters(config)
  clusters.update_clusters(all_clusters, trackings)

  print("Filling out expected costs and writing result to disk")
  fill_expected_costs(all_clusters, config)
  clusters.write_clusters(config, all_clusters)


def main(argv):
  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)

  clusterify(config)

  all_clusters = clusters.get_existing_clusters(config)
  driver_creator = DriverCreator(argv)

  tracking_to_po, po_to_cost = get_tracking_pos_costs_maps(
      config, driver_creator)

  fill_purchase_orders(all_clusters, tracking_to_po)
  all_clusters = clusters.merge_by_purchase_orders(all_clusters)
  fill_costs_by_po(all_clusters, po_to_cost)

  reconciliation_uploader = ReconciliationUploader(config)
  reconciliation_uploader.download_upload_clusters(all_clusters)
  clusters.write_clusters(config, all_clusters)


if __name__ == "__main__":
  main(sys.argv)
