import pickle
import os.path

from lib.objects_to_drive import ObjectsToDrive
from typing import Any

OUTPUT_FOLDER = "output"


class ObjectRetriever:
  """
  A class that stores and retrieves files from Drive (if possible) and locally otherwise.
  """

  def __init__(self, config) -> None:
    self.config = config

  def flush(self, obj, filename) -> None:
    if not os.path.exists(OUTPUT_FOLDER):
      os.mkdir(OUTPUT_FOLDER)

    local_file = OUTPUT_FOLDER + "/" + filename
    with open(local_file, 'wb') as stream:
      pickle.dump(obj, stream)

    objects_to_drive = ObjectsToDrive()
    objects_to_drive.save(self.config, filename, local_file)

  def load(self, filename) -> Any:
    objects_to_drive = ObjectsToDrive()
    from_drive = objects_to_drive.load(self.config, filename)
    if from_drive:
      return from_drive

    local_file = OUTPUT_FOLDER + "/" + filename
    if not os.path.exists(local_file):
      return {}

    with open(local_file, 'rb') as stream:
      return pickle.load(stream)
