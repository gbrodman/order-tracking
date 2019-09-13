import sheets_service
import googleapiclient.errors


class ObjectsToSheet:

  def __init__(self):
    self.service = sheets_service.create()

  def download_from_sheet(self, from_row_fn, base_sheet_id, tab_title):
    try:
      range = tab_title
      result = self.service.spreadsheets().values().get(
          spreadsheetId=base_sheet_id, range=range).execute()
      if 'values' not in result:  # blank sheet
        return []
      header = result['values'][0]
      values = result['values'][1:]  # ignore the header
      self.extend_values_to_header(header, values)
      return [from_row_fn(header, value) for value in values]
    except googleapiclient.errors.HttpError:
      # Tab doesn't exist
      self._create_tab(base_sheet_id, tab_title)
      return []

  def extend_values_to_header(self, header, values):
    for value in values:
      while len(value) < len(header):
        value.append('')

  def upload_to_sheet(self, objects, base_sheet_id, tab_title):
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

  def _write_header(self, objects, base_sheet_id, tab_title):
    header = objects[0].get_header()
    values = [header]
    body = {"values": values}
    self.service.spreadsheets().values().append(
        spreadsheetId=base_sheet_id,
        range=tab_title + "!A1:A1",
        valueInputOption="RAW",
        body=body).execute()

  def _clear_tab(self, base_sheet_id, tab_title):
    ranges = [tab_title]
    body = {"ranges": ranges}
    self.service.spreadsheets().values().batchClear(
        spreadsheetId=base_sheet_id, body=body).execute()

  def _create_tab(self, base_sheet_id, tab_title):
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
