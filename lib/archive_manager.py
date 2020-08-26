from lib.object_retriever import ObjectRetriever

ARCHIVES_FILENAME = "archives.pickle"


class ArchiveManager:

  def __init__(self, config):
    self.retriever = ObjectRetriever(config)
    self.archive_dict = self.retriever.load(ARCHIVES_FILENAME)

  def get_archive(self, name):
    return self.archive_dict[name]

  def has_archive(self, name):
    return name in self.archive_dict

  def put_archive(self, name, po_cost, trackings_cost) -> None:
    self.archive_dict[name] = (po_cost, trackings_cost)
    self.retriever.flush(self.archive_dict, ARCHIVES_FILENAME)
