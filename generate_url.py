import argparse
from lib import create_url


def main():
  parser = argparse.ArgumentParser(description='Create an add-to-cart URL')
  parser.add_argument("--no-smile", action="store_true")
  args, _ = parser.parse_known_args()

  asins = []
  while True:
    asin = input("Enter ASIN: ")
    if not asin:
      break
    asins.append(asin)

  if asins:
    print(create_url.create_url(asins, smile=not args.no_smile))


if __name__ == "__main__":
  main()
