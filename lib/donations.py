import datetime
import os
import pickle
import webbrowser

OUTPUT_FOLDER = "output"
LAST_MONTH_FILE = OUTPUT_FOLDER + "/last_month.pickle"

PAYPAL_URL = "https://www.paypal.me/gusbrodman"

def should_open_page():
  # Open a donation page the first time the script is run every month
  this_month = datetime.date.today().strftime("%Y-%m")
  if not os.path.exists(OUTPUT_FOLDER):
    os.mkdir(OUTPUT_FOLDER)

  if os.path.exists(LAST_MONTH_FILE):
    with open(LAST_MONTH_FILE, 'rb') as f:
      last_month = pickle.load(f)
      if last_month >= this_month:
        return False

  with open(LAST_MONTH_FILE, 'wb') as f:
    pickle.dump(this_month, f)
  return True

if should_open_page():
  webbrowser.open(PAYPAL_URL)
