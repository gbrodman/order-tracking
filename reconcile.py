import clusters
from tracking_output import TrackingOutput


def find_cluster(all_clusters, tracking):
  for cluster in all_clusters:
    if cluster.group == tracking.group and cluster.trackings.intersection(
        set(tracking.order_ids)):
      return cluster
  return None


def update_clusters(all_clusters, trackings_dict):
  for group, trackings in trackings_dict.items():
    for tracking in trackings:
      cluster = find_cluster(all_clusters, tracking)
      if cluster == None:
        cluster = clusters.Cluster(tracking.group)
        all_clusters.append(cluster)

      cluster.orders.update(tracking.order_ids)
      cluster.trackings.add(tracking.tracking_number)


if __name__ == "__main__":
  tracking_output = TrackingOutput()
  trackings_dict = tracking_output.get_existing_trackings()

  all_clusters = clusters.get_existing_clusters()
  update_clusters(all_clusters, trackings_dict)
  clusters.write_clusters(all_clusters)
  tracking_output.clear()
