import io
import pickle

from googleapiclient.http import MediaFileUpload
from googleapiclient.http import MediaIoBaseDownload
from tenacity import retry, stop_after_attempt, wait_exponential

from lib import drive_service


class ObjectsToDrive:

  def __init__(self):
    self.service = drive_service.create_drive()

  @retry(
      stop=stop_after_attempt(3),
      wait=wait_exponential(multiplier=1, min=2, max=16),
      reraise=True)
  def save(self, config, filename, local_filename):
    folder_id = self._get_folder_id(config)
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

  @retry(
      stop=stop_after_attempt(3),
      wait=wait_exponential(multiplier=1, min=2, max=16),
      reraise=True)
  def load(self, config, filename):
    folder_id = self._get_folder_id(config)
    files_in_folder = self._get_files_in_folder(folder_id)
    file_id = self._find_file_id(files_in_folder, filename)
    if file_id is None:
      return None
    return self._download_file(file_id)

  def _get_folder_id(self, config):
    if "driveFolderId" in config:
      return config["driveFolderId"]
    if "driveFolder" in config:
      return config["driveFolder"]
    raise Exception("Please include 'driveFolderId' in the config")

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
