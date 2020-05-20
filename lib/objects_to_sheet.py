import googleapiclient.errors
from tenacity import retry, stop_after_attempt, wait_exponential

from lib import drive_service


class ObjectsToSheet:

  def __init__(self) -> None:
    self.service = drive_service.create_sheets()

  @retry(
      stop=stop_after_attempt(3),
      wait=wait_exponential(multiplier=1, min=2, max=16),
      reraise=True)
  def download_from_sheet(self, from_row_fn, base_sheet_id, tab_title) -> list:
    try:
      range = tab_title
      value_render_option = "UNFORMATTED_VALUE"
      result = self.service.spreadsheets().values().get(
          spreadsheetId=base_sheet_id,
          range=range,
          valueRenderOption=value_render_option).execute()
      if 'values' not in result:  # blank sheet
        return []
      header = result['values'][0]
      values = result['values'][1:]  # ignore the header
      self._extend_values_to_header(header, values)
      return [from_row_fn(header, value) for value in values]
    except googleapiclient.errors.HttpError:
      # Tab doesn't exist
      self._create_tab(base_sheet_id, tab_title)
      return []

  @retry(
      stop=stop_after_attempt(3),
      wait=wait_exponential(multiplier=1, min=2, max=16),
      reraise=True)
  def upload_to_sheet(self,
                      objects,
                      base_sheet_id,
                      tab_title,
                      batch_update_body_fn=None) -> None:
    try:
      self._clear_tab(base_sheet_id, tab_title)
    except googleapiclient.errors.HttpError:
      # Tab doesn't exist
      self._create_tab(base_sheet_id, tab_title)

    if not objects:
      return

    self._write_header(objects, base_sheet_id, tab_title)

    values = [obj.to_row() for obj in objects]
    body = {"values": values}
    self.service.spreadsheets().values().append(
        spreadsheetId=base_sheet_id,
        range=tab_title + "!A1:A1",
        valueInputOption="USER_ENTERED",
        body=body).execute()
    if batch_update_body_fn:
      body = batch_update_body_fn(self.service, base_sheet_id, tab_title,
                                  len(values))
      self.service.spreadsheets().batchUpdate(
          spreadsheetId=base_sheet_id, body=body).execute()

  def _extend_values_to_header(self, header, values) -> None:
    for value in values:
      while len(value) < len(header):
        value.append('')

  def _write_header(self, objects, base_sheet_id, tab_title) -> None:
    header = objects[0].get_header()
    values = [header]
    body = {"values": values}
    self.service.spreadsheets().values().append(
        spreadsheetId=base_sheet_id,
        range=tab_title + "!A1:A1",
        valueInputOption="RAW",
        body=body).execute()

  def _clear_tab(self, base_sheet_id, tab_title) -> None:
    ranges = [tab_title]
    body = {"ranges": ranges}
    self.service.spreadsheets().values().batchClear(
        spreadsheetId=base_sheet_id, body=body).execute()

  def _create_tab(self, base_sheet_id, tab_title) -> None:
    batch_update_body = {
        'requests': [{
            'addSheet': {
                'properties': {
                    'title': tab_title
                }
            }
        }]
    }
    self.service.spreadsheets().batchUpdate(
        spreadsheetId=base_sheet_id, body=batch_update_body).execute()
