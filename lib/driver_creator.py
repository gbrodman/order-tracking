import argparse
import os
import sys
import urllib.request
import zipfile
from selenium import webdriver
from typing import Any


class DriverCreator:

  def __init__(self) -> None:
    parser = argparse.ArgumentParser(description='Driver creator')
    parser.add_argument("--no-headless", action="store_true")
    parser.add_argument("--firefox", action="store_true")
    self.args, _ = parser.parse_known_args()

  def new(self, user_data_dir=None) -> Any:
    if self.args.firefox:
      return self._new_firefox_driver()
    else:
      return self._new_chrome_driver(user_data_dir=user_data_dir)

  def fix_perms(self, path):
    for root, dirs, files in os.walk(path):
      for d in dirs:
        os.chmod(os.path.join(root, d), 0o755)
      for f in files:
        os.chmod(os.path.join(root, f), 0o755)

  def _create_osx_windows_driver(self,
                                 options,
                                 url,
                                 base_dir,
                                 binary_location,
                                 chromedriver_filename,
                                 user_data_dir=None):
    current_working_dir = os.getcwd()
    base = current_working_dir + base_dir
    download_location = base + "Chrome.zip"
    if not os.path.exists(base + binary_location):
      urllib.request.urlretrieve(url, download_location)
      os.chmod(download_location, 0o755)
      with zipfile.ZipFile(download_location, 'r') as zip_ref:
        zip_ref.extractall(base)
      self.fix_perms(base)
      os.remove(download_location)
    options.binary_location = (base + binary_location)

    if user_data_dir:
      options.add_argument(f"user-data-dir={user_data_dir}")
    return webdriver.Chrome(base + chromedriver_filename, options=options)

  def _create_osx_driver(self, options, user_data_dir=None):
    url = "https://github.com/macchrome/chromium/releases/download/v78.0.3901.0-r692376-macOS/Chromium.78.0.3901.0.sync.app.zip"
    return self._create_osx_windows_driver(options, url, "/chrome/osx/",
                                           "Chromium.app/Contents/MacOS/Chromium", "chromedriver",
                                           user_data_dir)

  def _create_windows_driver(self, options, user_data_dir=None):
    url = "https://github.com/RobRich999/Chromium_Clang/releases/download/v80.0.3982.0-r720336-win64/chrome.zip"
    return self._create_osx_windows_driver(options, url, "/chrome/windows/",
                                           "chrome-win32/chrome.exe", "chromedriver.exe",
                                           user_data_dir)

  def _new_chrome_driver(self, user_data_dir=None) -> Any:
    options = webdriver.chrome.options.Options()
    options.headless = not self.args.no_headless
    options.add_argument("--log-level=3")

    # no idea why, but it's a million times slower in headless mode in Windows without these lines
    options.add_argument("--proxy-server='direct://'")
    options.add_argument("--proxy-bypass-list=*")

    # Always fully render browser windows, even when backgrounded.
    options.add_argument("--disable-backgrounding-occluded-windows")

    # reduce Windows log spam
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    if sys.platform.startswith("darwin"):  # osx
      driver = self._create_osx_driver(options, user_data_dir)
    elif sys.platform.startswith("win"):  # windows
      driver = self._create_windows_driver(options, user_data_dir)
    else:  # ??? probably Linux. Linux users can figure this out themselves
      driver = webdriver.Chrome(options=options)

    driver.set_window_size(2000, 1600)
    driver.implicitly_wait(10)
    driver.set_page_load_timeout(10)
    return driver

  def _new_firefox_driver(self) -> Any:
    profile = webdriver.FirefoxProfile()
    profile.native_events_enabled = False
    options = webdriver.firefox.options.Options()
    options.headless = self.headless
    driver = webdriver.Firefox(profile, options=options)
    driver.set_window_size(1500, 1200)
    driver.set_page_load_timeout(60)
    return driver
