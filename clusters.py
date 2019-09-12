import pickle
import os.path

OUTPUT_FOLDER = "output"
CLUSTERS_FILE = OUTPUT_FOLDER + "/clusters.pickle"


def from_row(header, row):
  orders = set(
      row[header.index('Orders')].split(',')) if 'Orders' in header else set()
  trackings = set(row[header.index('Trackings')].split(
      ',')) if 'Trackings' in header else set()
  expected_cost = float(row[header.index('Amount Billed')].replace(
      ',', '').replace('$', '')) if 'Amount Billed' in header else 0.0
  tracked_cost = float(row[header.index('Amount Reimbursed')].replace(
      ',', '').replace('$', '')) if 'Amount Reimbursed' in header else 0.0
  last_ship_date = row[header.index(
      'Last Ship Date')] if 'Last Ship Date' in header else '0'
  pos = set(row[header.index('POs')].split(',')) if 'POs' in header else set()
  group = row[header.index('Group')] if 'Group' in header else ''
  adjustment = float(row[header.index('Manual Cost Adjustment')].replace(
      ',', '').replace('$', '')) if 'Manual Cost Adjustment' in header else 0.0
  cluster = Cluster(group)
  cluster._initiate(orders, trackings, group, expected_cost, tracked_cost,
                    last_ship_date, pos, adjustment)
  return cluster


class Cluster:

  def __init__(self, group):
    self._initiate(set(), set(), group, 0, 0, '0', set(), 0.0)

  def _initiate(self,
                orders,
                trackings,
                group,
                expected_cost,
                tracked_cost,
                last_ship_date='0',
                purchase_orders=set(),
                adjustment=0.0):
    self.orders = orders
    self.trackings = trackings
    self.group = group
    self.expected_cost = expected_cost
    self.tracked_cost = tracked_cost
    self.last_ship_date = last_ship_date
    self.purchase_orders = purchase_orders
    self.adjustment = adjustment

  def __setstate__(self, state):
    self._initiate(**state)

  def __str__(self):
    return "orders: %s, trackings: %s, group: %s, expected cost: %s, tracked cost: %s, last_ship_date: %s, purchase_orders: %s, adjustment: %s" % (
        str(self.orders), str(self.trackings), self.group,
        str(self.expected_cost), str(self.tracked_cost), self.last_ship_date,
        str(self.purchase_orders), str(self.adjustment))

  def get_header(self):
    return [
        "Orders", "Trackings", "Amount Billed", "Amount Reimbursed",
        "Last Ship Date", "POs", "Group", "Manual Cost Adjustment", "Total Diff"
    ]

  def to_row(self):
    return [
        ",".join(self.orders), ",".join(self.trackings), self.expected_cost,
        self.tracked_cost, self.last_ship_date, ",".join(self.purchase_orders),
        self.group, self.adjustment,
        self.expected_cost - self.tracked_cost - self.adjustment
    ]

  def merge_with(self, other):
    self.orders.update(other.orders)
    self.trackings.update(other.trackings)
    self.expected_cost += other.expected_cost
    self.tracked_cost += other.tracked_cost
    self.last_ship_date = max(self.last_ship_date, other.last_ship_date)
    self.purchase_orders.update(other.purchase_orders)
    self.adjustment += other.adjustment


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
    if cluster.group == tracking.group and cluster.orders.intersection(
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
      cluster.last_ship_date = max(cluster.last_ship_date, tracking.ship_date)


def merge_by_purchase_orders(clusters):
  while True:
    prev_length = len(clusters)
    clusters = run_merge_iteration(clusters)
    if len(clusters) == prev_length:
      break
  return clusters


def run_merge_iteration(clusters):
  result = []
  for cluster in clusters:
    to_merge = find_by_purchase_orders(cluster, result)
    if to_merge:
      to_merge.merge_with(cluster)
    else:
      result.append(cluster)
  return result


def find_by_purchase_orders(cluster, all_clusters):
  if not cluster.purchase_orders:
    return None

  for candidate in all_clusters:
    if candidate.purchase_orders.intersection(cluster.purchase_orders):
      return candidate

  return None
