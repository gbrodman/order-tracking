from selenium import webdriver


class DriverCreator:

  def __init__(self, args):
    args = [str(arg).upper() for arg in args]
    if "--FIREFOX" in args:
      self.type = "FIREFOX"
    else:
      self.type = "CHROME"

    if "--NO-HEADLESS" in args:
      self.headless = False
    else:
      self.headless = True

  def new(self):
    if self.type == "CHROME":
      return self._new_chrome_driver()
    elif self.type == "FIREFOX":
      return self._new_firefox_driver()
    raise Exception("Unknown type " + self.type)

  def _new_chrome_driver(self):
    options = webdriver.chrome.options.Options()
    options.headless = self.headless
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(10)
    driver.set_page_load_timeout(10)
    return driver

  def _new_firefox_driver(self):
    profile = webdriver.FirefoxProfile()
    profile.native_events_enabled = False
    options = webdriver.firefox.options.Options()
    options.headless = self.headless
    driver = webdriver.Firefox(profile, options=options)
    driver.set_page_load_timeout(60)
    return driver
