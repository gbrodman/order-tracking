# order-tracking

This is a set of Python scripts meant for streamlining and automating the process of reconciling one's orders with buying groups. In a basic sense, it automates the retrieval of tracking information, upload to buying groups' sites, and order reconciliation after reimbursement. The main purposes of these scripts is so that one can look at a single Google Sheet and immediately know what orders have been properly tracked and reimbursed by the buying groups, and to give the user the tools to fix any issues that may arise.

# What This Does

There are two main tasks. They are:

### get_order_tracking.py: 

This script does the following:

- Parses unread shipping notification emails from the last 45 days from Amazon or Best Buy. 
- Parses out a set of information from those emails and associated emails, including tracking number(s), order number(s), order costs, email addresses, order URLs, and shipping dates and saves that information to disk and to Drive. 
- Uploads those tracking numbers to the order tracking systems of groups like Pointsmaker, MYS, or USA.
- Groups together orders or tracking numbers that are bunched together by Amazon or Best Buy for later reconciliation (e.g. two orders are grouped together if they ship in the same shipment). 
- Emails you (the user) a list of tracking/order numbers that it found, for sanity checking.

If it cannot parse an email for some reason, it will mark the email as unread so that you can look at it manually later. This sometimes happens if Amazon is being slow -- in these cases, there is no harm in running the script again. 

### reconcile.py

This is the script for reconciliation. It does the following:

- Loads in the groups of tracking numbers / orders from `get_tracking_numbers.py`.
- Fills out the reimbursed costs when it can (for groups like Pointsmaker, MYS, or USA). This entails going into the group's website and parsing out the mapping from tracking number to reimbursed cost.
- Groups orders together by purchase order (if applicable, only USA).
- Applies manual adjustments (see "Sheets Output" below).
- Uploads the reconciliation output to a Google Sheet in a human-readable format. See "Sheets Output" below for more information.

# Limitations

- This will only work for one email account at a time
- This will only work for GMail
- Auto-uploading only works for USA and sites whose websites are of the same format as Pointsmaker or MYS
- All addresses must contain a key that uniquely identifies which buying group the address belongs to. The default is a part of the group's address.

## Prerequisites

- One must be able to run a headless browser with Selenium, either Chrome or Firefox. Chromedriver or geckodriver (respectively) must be on the user's PATH.
- Python3 and pip3 (these should come together)

## Instructions (basic)

- Disconnect from any VPNs that might interfere (they might or might not cause you some network connectivity issues)
- If you don't have it already, add either Chromedriver or Geckodriver to your PATH. The default is Chrome; download it from [here](https://sites.google.com/a/chromium.org/chromedriver/home) and add it to your PATH (this will vary based on operating system, search on Google for results particular to your system).
- Enable IMAP in GMail--go to the Settings page, then the "Forwarding and POP/IMAP" tab, then make sure IMAP is enabled
- `pip3 install pyyaml selenium google-api-python-client google-auth-oauthlib bs4`
- Copy config.yml.template to config.yml
- In config.yml, fill in the values for your email, password, and buying group info. For GMail, you should use an application-specific password. Also fill in your username/password for the buying groups you wish to use.
- For the reconciliation sheet ID, see "Sheets Configuration" below
- Run `python3 get_tracking_numbers.py` followed by `python3 reconcile.py`

### Arguments

- `--no-headless` to run in a standard browser, rather than a headless browser. This is useful if you want to see what the Selenium browser automation is actually doing.
- `--firefox` to run using Firefox/Geckodriver rather than Chrome

## Sheets Configuration

TODO

## Sheets Output

TODO

## Google Sheets Integration (optional)

If you wish to upload order number + tracking number to a Google Sheet, uncomment out the relevant section in the configuration, then create a credentials file ([see example here](https://www.makeuseof.com/tag/read-write-google-sheets-python/)). Note that the account key you create should be based on a non-UI cron-job type account (a service account key). Take the resulting credentials file and save it as `creds.json` in the same directory as the scripts. Also, [enable the Sheets API for your project](https://console.developers.google.com/apis/api/sheets.googleapis.com/overview).

Create the spreadsheet, then include the base spreadsheet ID in the config

## Donations

This software is completely free, licensed under the Apache 2.0 license. However, if you feel like you wish to donate some money to me, feel free to send any amount of money through Paypal to `gustav@gustav.dev`.
