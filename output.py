import pickle
import os.path

OUTPUT_FOLDER = "output"
TRACKINGS_FILE = OUTPUT_FOLDER + "/trackings.pickle"


class TrackingOutput:

  def __init__(self, trackings):
    self.trackings = trackings

  def save_trackings(self):
    old_trackings = self.get_old_trackings()
    merged_trackings = self.merge_trackings(old_trackings)
    self.write_merged(merged_trackings)

  def write_merged(self, merged_trackings):
    if not os.path.exists(OUTPUT_FOLDER):
      os.mkdir(OUTPUT_FOLDER)

    with open(TRACKINGS_FILE, 'wb') as output:
      pickle.dump(merged_trackings, output)

  def merge_trackings(self, old_trackings):
    for group, group_trackings in self.trackings.items():
      if group in old_trackings:
        old_group_trackings = old_trackings[group]
        old_tracking_numbers = set(
            [ogt.tracking_number for ogt in old_group_trackings])
        for new_group_tracking in group_trackings:
          if new_group_tracking.tracking_number not in old_tracking_numbers:
            old_group_trackings.append(new_group_tracking)
        old_trackings[group] = old_group_trackings
      else:
        old_trackings[group] = group_trackings
    return old_trackings

  def get_old_trackings(self):
    if not os.path.exists(TRACKINGS_FILE):
      return {}

    with open(TRACKINGS_FILE, 'rb') as tracking_file_stream:
      return pickle.load(tracking_file_stream)
