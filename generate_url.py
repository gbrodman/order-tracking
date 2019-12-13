import argparse
from lib import create_url


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description='Create an add-to-cart URL')
  parser.add_argument("--no_smile", action="store_true")
  args, _ = parser.parse_known_args()

  asins = []
  while True:
    asin = input("Enter ASIN: ")
    if not asin:
      break
    asins.append(asin)

  if asins:
    print(create_url.create_url(asins))