import pickle
import os.path

OUTPUT_FOLDER = "output"
CLUSTERS_FILE = OUTPUT_FOLDER + "/clusters.pickle"


class Cluster:

  def __init__(self, group):
    self.orders = set()
    self.trackings = set()
    self.group = group
    self.expected_cost = 0
    self.tracked_cost = 0

  def __str__(self):
    return "orders: %s, trackings: %s, group: %s, expected cost: %s, tracked cost: %s" % (
        str(self.orders), str(self.trackings), self.group,
        str(self.expected_cost), str(self.tracked_cost))


def dedupe_clusters(clusters):
  result = []
  seen_tracking_ids = set()
  for cluster in clusters:
    if not cluster.trackings.intersection(seen_tracking_ids):
      seen_tracking_ids.update(cluster.trackings)
      result.append(cluster)
  return result


def write_clusters(clusters):
  clusters = dedupe_clusters(clusters)
  if not os.path.exists(OUTPUT_FOLDER):
    os.mkdir(OUTPUT_FOLDER)

  with open(CLUSTERS_FILE, 'wb') as output:
    pickle.dump(clusters, output)


def get_existing_clusters():
  if not os.path.exists(CLUSTERS_FILE):
    return []

  with open(CLUSTERS_FILE, 'rb') as clusters_file_stream:
    clusters = pickle.load(clusters_file_stream)
  return dedupe_clusters(clusters)


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
        cluster = Cluster(tracking.group)
        all_clusters.append(cluster)

      cluster.orders.update(tracking.order_ids)
      cluster.trackings.add(tracking.tracking_number)
