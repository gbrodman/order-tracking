import time
import re
from selenium import webdriver

LOGIN_EMAIL_FIELD = "fldEmail"
LOGIN_PASSWORD_FIELD = "fldPassword"
LOGIN_BUTTON_SELECTOR = "//button[contains(text(), 'Login')]"

SUBMIT_BUTTON_SELECTOR = "//*[contains(text(), 'SUBMIT')]"

RESULT_SELECTOR = "//*[contains(text(), 'record(s) effected')]"
RESULT_REGEX = r"(\d+) record\(s\) effected"

BASE_URL_FORMAT = "https://www.%s.com"
MANAGEMENT_URL_FORMAT = "https://www.%s.com/p/it@orders-all/"

USA_LOGIN_URL = "https://usabuying.group/login"
USA_TRACKING_URL = "https://usabuying.group/trackings"

def load_page(driver, url):
    driver.get(url)
    time.sleep(1)

def upload_mys_pm(numbers, site, username, password):
    driver = webdriver.Chrome()
    try:
        driver.implicitly_wait(10)
        load_page(driver, BASE_URL_FORMAT % site)
        driver.find_element_by_name(LOGIN_EMAIL_FIELD).send_keys(username)
        driver.find_element_by_name(LOGIN_PASSWORD_FIELD).send_keys(password)
        driver.find_element_by_xpath(LOGIN_BUTTON_SELECTOR).click()
        time.sleep(1)
        load_page(driver, MANAGEMENT_URL_FORMAT % site)
        driver.find_element_by_xpath("//textarea").send_keys('\n'.join(numbers))
        driver.find_element_by_xpath(SUBMIT_BUTTON_SELECTOR).click()
        result_text = driver.find_element_by_xpath(RESULT_SELECTOR).text
        match = re.match(RESULT_REGEX, result_text)
        num_records = int(match.group(1))

        if num_records != len(numbers):
            raise Exception("Expected to create %d records for group %s but created %d, tried to upload %s" % (len(numbers), site, num_records, str(numbers)))
    finally:
        driver.close()

def upload_usa(numbers, username, password):
    driver = webdriver.Chrome()
    try:
        driver.implicitly_wait(10)
        load_page(driver, USA_LOGIN_URL)
        driver.find_element_by_name("credentials").send_keys(username)
        driver.find_element_by_name("password").send_keys(password)
        # for some reason there's an invalid login button in either the first or second array spot (randomly)
        for element in driver.find_elements_by_name("log-me-in"):
            try:
                element.click()
            except:
                pass

        time.sleep(2)
        load_page(driver, USA_TRACKING_URL)
        driver.find_element_by_xpath("//*[contains(text(), ' Add')]").click()
        driver.find_element_by_xpath("//textarea").send_keys("\n".join(numbers))
        driver.find_element_by_xpath("//*[contains(text(), 'Submit')]").click()
        # TODO: raise errors if the tracking numbers already existed
    finally:
        driver.close()

def upload(numbers, site, username, password):
    if site == "mysbuyinggroup" or site == "pointsmaker":
        upload_mys_pm(numbers, site, username, password)
    elif site == "usa":
        upload_usa(numbers, username, password)
    else:
        raise Exception("Unknown site " + site)
