from .. import driver_creator
from .. import create_url

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
      driver.get(create_url.create_url(asins))
      time.sleep(2)
      table = driver.find_elements_by_tag_name("table")[0]
      rows = table.find_elements_by_tag_name("tr")[1:]
      price_tds = table.find_elements_by_xpath("//td[contains(@class, 'price') and contains(@class, 'item-row')]")
      for i in range(len(rows)):
        if len(price_tds) <= i:
          break
        row = rows[i]
        asin = row.find_elements_by_tag_name('a')[0].get_attribute(
            'href').split('/')[-1]
        price_str = price_tds[i].text.replace("$", '').replace(",", '')
        result[asin] = float(price_str)
      return result
    finally:
      driver.close()
