from selenium import webdriver
from typing import Any


class DriverCreator:

  def __init__(self, args) -> None:
    args = [str(arg).upper() for arg in args]
    if "--FIREFOX" in args:
      self.type = "FIREFOX"
    else:
      self.type = "CHROME"

    if "--NO-HEADLESS" in args:
      self.headless = False
    else:
      self.headless = True

  def new(self) -> Any:
    if self.type == "CHROME":
      return self._new_chrome_driver()
    elif self.type == "FIREFOX":
      return self._new_firefox_driver()
    raise Exception("Unknown type " + self.type)

  def _new_chrome_driver(self) -> Any:
    options = webdriver.chrome.options.Options()
    options.headless = self.headless
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
