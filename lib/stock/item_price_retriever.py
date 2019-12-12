from .. import driver_creator

import random
import time

CART_URL_FORMAT = "https://amazon.com/gp/aws/cart/add.html?&ASIN.1=%s&Quantity.1=1"


class ItemPriceRetriever:

  def __init__(self):
    self.dc = driver_creator.DriverCreator()

  def get_prices(self, asins):
    driver = self.dc.new()
    try:
      driver.implicitly_wait(1)
      result = {}
      for asin in asins:
        time.sleep(random.randint(1, 2))
        driver.get(CART_URL_FORMAT % asin)
        time.sleep(2)
        price_tds = driver.find_elements_by_xpath(
            "//td[contains(@class, 'price') and contains(@class, 'item-row')]")
        if price_tds:
          result[asin] = float(price_tds[0].text.replace("$",
                                                         '').replace(",", ''))
        else:
          # Nope
          result[asin] = None
      return result
    finally:
      driver.close()
