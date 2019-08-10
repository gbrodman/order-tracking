# order-tracking

This is a set of Python scripts that uses Selenium to retrieve unread Amazon shipping notification emails, parse out the tracking number and other information from those emails, and (if configured) automatically upload those tracking numbers to Pointsmaker, MYS, or USA buying groups, as appropriate. Regardless of uploading, it will group the tracking numbers by buying group and email them to you, for your own verification, tracking, or to upload to other buying groups. 

NOTE: for now I believe it only works with personal Amazon accounts

## Prerequisites

- This will only work with one email account, and I've only tested with GMail
- All addresses must contain a key that uniquely identifies which buying group the address belongs to. The default is a part of the group's address.
- Auto-uploading only works with PM, MYS, and USA
- One must be able to run a headless browser with Selenium, either Chrome or Firefox
- Python3

## Instructions (basic)

- `pip3 install pyyaml selenium`
- Copy config.yml.template to config.yml
- In config.yml, fill in the values for your email, password, and buying group info. For GMail, you should use an application-specific password. 
- If you wish to use auto-upload, fill in your username/password for PM, MYS, USA buying groups 
- Run `python3 get_tracking_numbers.py` 
  - Optional argument of "chrome" or "firefox" to tell the script which browser to use. Default is Chrome.
