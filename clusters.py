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


def write_clusters(clusters):
  if not os.path.exists(OUTPUT_FOLDER):
    os.mkdir(OUTPUT_FOLDER)

  with open(CLUSTERS_FILE, 'wb') as output:
    pickle.dump(clusters, output)


def get_existing_clusters():
  if not os.path.exists(CLUSTERS_FILE):
    return []

  with open(CLUSTERS_FILE, 'rb') as clusters_file_stream:
    return pickle.load(clusters_file_stream)

