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


if __name__ == "__main__":
  profile_str = input("Enter profiles, e.g. 1-3, 6-7: ")
  profile_range = PageRange(profile_str)
  asin_url = str(input("Enter the ASIN URL: "))
  print("Opening URL in your Chrome Profiles...")

  for i in profile_range.pages:
    command = get_chrome_command(i)
    print(command)
    webbrowser.get(command).open(asin_url)
