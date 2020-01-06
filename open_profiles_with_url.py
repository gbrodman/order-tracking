import argparse
import json
import os
import sys
import webbrowser
from pagerange import PageRange


def get_chrome_command(i):
  if sys.platform.startswith("darwin"):  # osx
    return f'/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --profile-directory="Profile {i}" --start-maximized %s &'
  elif sys.platform.startswith("win"):  # windows
    return f'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe %s --profile-directory="Profile {i}" --start-maximized'
  else:
    raise Exception("This script doesn't work on Linux")


def print_profile_list():
  print("Mapping of profile numbers to names:")
  if sys.platform.startswith("darwin"):  # osx
    path = "~/Library/Application Support/Google/Chrome/Local State"
  elif sys.platform.startswith("win"):  # windows
    path = "~/AppData/Local/Google/Chrome/User Data/Local State"
  else:
    raise Exception("This script doesn't work on Linux")
  path = os.path.expanduser(path)
  with open(path) as json_file:
    data = json.load(json_file)
  profiles = data['profile']['info_cache']
  for name, profile_data in profiles.items():
    casual_name = profile_data['name']
    print(f"{name}  |  {casual_name}")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description='Driver creator')
  parser.add_argument("-l", "--list", action="store_true")
  args, _ = parser.parse_known_args()

  if args.list:
    print_profile_list()

  profile_str = input("Enter profiles, e.g. 1-3, 6-7: ")
  profile_range = PageRange(profile_str)
  asin_url = str(input("Enter the ASIN URL: "))
  print("Opening URL in your Chrome Profiles...")

  for i in profile_range.pages:
    command = get_chrome_command(i)
    print(command)
    webbrowser.get(command).open(asin_url)
