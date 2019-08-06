from selenium import webdriver
from selenium.webdriver.firefox.options import Options

CHROME = "CHROME"
FIREFOX = "FIREFOX"

class DriverCreator:

    def __init__(self, type = CHROME):
        self.type = type

    def new(self):
        if self.type == CHROME:
            return self._new_chrome_driver()
        elif self.type == FIREFOX:
            return self._new_firefox_driver()
        raise Exception("Unknown type " + self.type)

    def _new_chrome_driver(self):
        driver = webdriver.Chrome()
        driver.implicitly_wait(10)
        driver.set_page_load_timeout(10)
        return driver

    def _new_firefox_driver(self):
        profile = webdriver.FirefoxProfile()
        profile.native_events_enabled = False
        options = Options()
        options.headless = True
        driver = webdriver.Firefox(profile, options=options)
        driver.set_page_load_timeout(60)
        return driver
