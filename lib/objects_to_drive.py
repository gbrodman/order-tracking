from lib import drive_service
import io
import pickle
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.http import MediaFileUpload

# pickle hacks
import sys
from lib import tracking
sys.modules['tracking'] = tracking
from lib import clusters
sys.modules['clusters'] = clusters

class ObjectsToDrive:

  def __init__(self):
    self.service = drive_service.create_drive()

  def save(self, folder_id, filename, local_filename):
    file_metadata = {"name": filename, "mimeType": "*/*"}
    media = MediaFileUpload(local_filename, mimetype='*/*', resumable=True)

    files_in_folder = self._get_files_in_folder(folder_id)
    file_id = self._find_file_id(files_in_folder, filename)
    if file_id is None:
      # create
      file_metadata["parents"] = [folder_id]
      self.service.files().create(
          body=file_metadata, media_body=media).execute()
    else:
      # update
      self.service.files().update(fileId=file_id, media_body=media).execute()

  def load(self, folder_id, filename):
    files_in_folder = self._get_files_in_folder(folder_id)
    file_id = self._find_file_id(files_in_folder, filename)
    if file_id is None:
      return None
    return self._download_file(file_id)

  def _find_file_id(self, files, filename):
    for file in files:
      if file['name'] == filename:
        return file['id']
    return None

  def _get_files_in_folder(self, folder_id):
    return self.service.files().list(
        q="'%s' in parents" % folder_id,
        fields='nextPageToken, files(id, name)').execute()['files']

  def _download_file(self, file_id):
    request = self.service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
      status, done = downloader.next_chunk()
    fh.seek(0)
    return pickle.load(fh)
