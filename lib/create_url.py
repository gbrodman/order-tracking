PREFIX = "https://smile.amazon.com/gp/aws/cart/add.html?"


def create_url(asins):
  url = PREFIX
  for i in range(1, len(asins) + 1):
    asin = asins[i - 1]
    url += f"&ASIN.{i}={asin}&Quantity.{i}=10"
  return url
