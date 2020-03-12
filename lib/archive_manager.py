import os
import pickle

from lib.objects_to_drive import ObjectsToDrive
from tqdm import tqdm
from typing import Any, Dict, List, Set

OUTPUT_FOLDER = "output"
ARCHIVES_FILENAME = "archives.pickle"
ARCHIVES_FILE = OUTPUT_FOLDER + "/" + ARCHIVES_FILENAME


class ArchiveManager:

  def __init__(self, config):
    self.config = config
    self.archive_dict = self.load_archive_dict()

  def get_archive(self, name):
    return self.archive_dict[name]

  def has_archive(self, name):
    return name in self.archive_dict

  def load_archive_dict(self):
    objects_to_drive = ObjectsToDrive()
    from_drive = objects_to_drive.load(self.config, ARCHIVES_FILENAME)
    if from_drive:
      return from_drive

    if not os.path.exists(ARCHIVES_FILE):
      return {}

    with open(ARCHIVES_FILE, 'rb') as stream:
      return pickle.load(stream)

  def put_archive(self, name, po_cost, trackings_cost) -> None:
    self.archive_dict[name] = (po_cost, trackings_cost)
    if not os.path.exists(OUTPUT_FOLDER):
      os.mkdir(OUTPUT_FOLDER)

    with open(ARCHIVES_FILE, 'wb') as stream:
      pickle.dump(self.archive_dict, stream)

    objects_to_drive = ObjectsToDrive()
    objects_to_drive.save(self.config, ARCHIVES_FILENAME, ARCHIVES_FILE)
