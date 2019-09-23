#!/usr/bin/env python3

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


def get_tracked_costs(config, driver_creator):
  print("Loading tracked costs. This will take several minutes.")
  group_site_manager = GroupSiteManager(config, driver_creator)
  tracked_costs = {}
  for group in config['groups'].keys():
    tracked_costs.update(group_site_manager.get_tracked_costs(group))

  return tracked_costs


# Take the reimbursed costs we found and write them into the Tracking objects
def fill_tracking_costs_and_upload(config, tracked_costs):
  tracking_output = TrackingOutput()
  existing_trackings = tracking_output.get_existing_trackings(config)
  for tracking in existing_trackings:
    if tracking.tracking_number in tracked_costs:
      tracking.tracked_cost = tracked_costs[tracking.tracking_number]
  tracking_output.save_trackings(config, existing_trackings)
  # also upload it
  tracking_uploader = TrackingUploader(config)
  tracking_uploader.upload_all_trackings(existing_trackings)


def fill_tracked_costs(all_clusters, config, driver_creator):
  tracked_costs = get_tracked_costs(config, driver_creator)
  fill_tracking_costs_and_upload(config, tracked_costs)
  for cluster in all_clusters:
    tracked_cost = sum([
        tracked_costs.get(tracking_number, 0.0)
        for tracking_number in cluster.trackings
    ])
    cluster.tracked_cost = tracked_cost


def fill_purchase_orders(all_clusters, config, driver_creator):
  print("Filling purchase_orders")
  group_site_manager = GroupSiteManager(config, driver_creator)
  tracking_to_purchase_order = group_site_manager.get_tracking_to_purchase_order(
      'usa')

  for cluster in all_clusters:
    for tracking in cluster.trackings:
      if tracking in tracking_to_purchase_order:
        cluster.purchase_orders.add(tracking_to_purchase_order[tracking])


def fill_costs_by_po(all_clusters, config, driver_creator):
  print("Finding costs by PO")
  group_site_manager = GroupSiteManager(config, driver_creator)
  po_to_price = group_site_manager.get_po_to_price('usa')
  for cluster in all_clusters:
    if cluster.purchase_orders:
      cluster.tracked_cost = sum(
          [po_to_price.get(po, 0.0) for po in cluster.purchase_orders])


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

  fill_tracked_costs(all_clusters, config, driver_creator)
  fill_purchase_orders(all_clusters, config, driver_creator)
  all_clusters = clusters.merge_by_purchase_orders(all_clusters)
  fill_costs_by_po(all_clusters, config, driver_creator)

  reconciliation_uploader = ReconciliationUploader(config)
  reconciliation_uploader.download_upload_clusters(all_clusters)
  clusters.write_clusters(config, all_clusters)

if __name__ == "__main__":
  main(sys.argv)
