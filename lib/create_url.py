PREFIX = "https://amazon.com/gp/aws/cart/add.html?"
SMILE_PREFIX = "https://smile.amazon.com/gp/aws/cart/add.html?"


def create_url(asins, smile=True):
  url = SMILE_PREFIX if smile else PREFIX
  for i, asin in enumerate(asins):
    url += f"&ASIN.{i+1}={asin}&Quantity.{i+1}=10"
  return url
