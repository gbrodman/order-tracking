import clusters
import yaml
import sys
from expected_costs import ExpectedCosts
from group_site_manager import GroupSiteManager
from driver_creator import DriverCreator
from reconciliation_uploader import ReconciliationUploader
from tracking_output import TrackingOutput
from tracking_uploader import TrackingUploader

CONFIG_FILE = "config.yml"


def get_tracked_costs_by_group(all_clusters, config, driver_creator):
  groups = set()
  for cluster in all_clusters:
    groups.add(cluster.group)

  tracked_costs_by_group = {}
  for group in groups:
    group_site_manager = GroupSiteManager(config, driver_creator)
    tracked_costs_by_group[group] = group_site_manager.get_tracked_costs(group)

  return tracked_costs_by_group


# Take the reimbursed costs we found and write them into the Tracking objects
def fill_tracking_costs_and_upload(config, tracked_costs_by_group):
  tracking_output = TrackingOutput()
  existing_trackings = tracking_output.get_existing_trackings(config)
  for group, trackings in existing_trackings.items():
    if group not in tracked_costs_by_group:
      continue
    this_group = tracked_costs_by_group[group]
    for tracking in trackings:
      if tracking.tracking_number in this_group:
        tracking.tracked_cost = this_group[tracking.tracking_number]
  tracking_output.save_trackings(config, existing_trackings)
  # get a list of the trackings and upload it
  tracking_uploader = TrackingUploader(config)
  trackings_list = []
  for trackings in existing_trackings.values():
    trackings_list.extend(trackings)
  tracking_uploader.upload_all_trackings(trackings_list)


def fill_tracked_costs(all_clusters, config, driver_creator):
  tracked_costs_by_group = get_tracked_costs_by_group(all_clusters, config,
                                                      driver_creator)
  fill_tracking_costs_and_upload(config, tracked_costs_by_group)
  for cluster in all_clusters:
    group = cluster.group
    if group in tracked_costs_by_group:
      tracked_cost = sum([
          tracked_costs_by_group[group].get(tracking_number, 0.0)
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


if __name__ == "__main__":
  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)

  all_clusters = clusters.get_existing_clusters(config)
  driver_creator = DriverCreator(sys.argv)

  fill_tracked_costs(all_clusters, config, driver_creator)
  fill_purchase_orders(all_clusters, config, driver_creator)
  all_clusters = clusters.merge_by_purchase_orders(all_clusters)
  fill_costs_by_po(all_clusters, config, driver_creator)

  reconciliation_uploader = ReconciliationUploader(config)
  reconciliation_uploader.download_upload_clusters(all_clusters)
  clusters.write_clusters(config, all_clusters)
