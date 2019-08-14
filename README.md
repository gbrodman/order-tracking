# order-tracking

This is a set of Python scripts that uses Selenium to retrieve unread Amazon shipping notification emails, parse out the tracking number and other information from those emails, and (if configured) automatically upload those tracking numbers to Pointsmaker, MYS, or USA buying groups, as appropriate. Regardless of uploading, it will group the tracking numbers by buying group and email them to you, for your own verification, tracking, or to upload to other buying groups. 

The script will search for unread Amazon shipment notifications in your email in the past 30 days (this is configurable). If it cannot parse an email for some reason, it will mark the email as unread so that you can look at it manually later. If there is another failure (e.g. when uploading the tracking numbers), it will mark all of the emails it found as unread so that it can be run again later.

## Limitations

- This will only work for one email account at a time
- This will only work for GMail
- Auto-uploading only works for PM, MYS, and USA

## Prerequisites

- All addresses must contain a key that uniquely identifies which buying group the address belongs to. The default is a part of the group's address.
- One must be able to run a headless browser with Selenium, either Chrome or Firefox. Chromedriver or geckodriver (respectively) must be on the user's PATH.
- Python3 and pip3 (these should come together)

## Instructions (basic)

- Disconnect from any VPNs that might interfere (they might or might not cause you some network connectivity issues)
- If you don't have it already, add either Chromedriver or Geckodriver to your PATH. The default is Chrome; download it from [here](https://sites.google.com/a/chromium.org/chromedriver/home) and add it to your PATH (this will vary based on operating system, search on Google for results particular to your system).
- Enable IMAP in GMail--go to the Settings page, then the "Forwarding and POP/IMAP" tab, then make sure IMAP is enabled
- `pip3 install pyyaml selenium google-api-python-client google-auth-oauthlib`
- Copy config.yml.template to config.yml
- In config.yml, fill in the values for your email, password, and buying group info. For GMail, you should use an application-specific password. 
- If you wish to use auto-upload, fill in your username/password for PM, MYS, USA buying groups 
- Run `python3 get_tracking_numbers.py` 

### Arguments

- `--no-headless` to run in a standard browser, rather than a headless browser. This is useful if you want to see what the Selenium browser automation is actually doing.
- `--firefox` to run using Firefox/Geckodriver rather than Chrome

## Google Sheets Integration (optional)

If you wish to upload order number + tracking number to a Google Sheet, uncomment out the relevant section in the configuration, then create a credentials file ([see example here](https://www.makeuseof.com/tag/read-write-google-sheets-python/)). Note that the account key you create should be based on a non-UI cron-job type account (a service account key). Take the resulting credentials file and save it as `creds.json` in the same directory as the scripts. Also, [enable the Sheets API for your project](https://console.developers.google.com/apis/api/sheets.googleapis.com/overview).

Create the spreadsheet, then include the base spreadsheet ID in the config, and the desired tab title per buying group. Note: the base spreadsheet ID is the long-ish string of characters that appears after the "d/" in the Google Sheets URL. Make sure to give your service account (in the linked instructions) permissions to access the sheet.

The script will create the tab and header if they don't exist, then append tracking number info to the end of the sheet. Currently, the columns in order are:
- Tracking number
- Order number
- Cost in that shipment (only available for personal Amazon accounts)
- Email address to which the shipping notifcation was sent (NB: not necessarily the account you're reading the email with)

An example:

![spreadsheet-example](https://lh3.googleusercontent.com/kbDeqdo3nWcuQkUAAViQ3nGhw_0GeuyJ9M6bcTS8vE69lx0CSqEcm4OJLe3raPnUhiEtp8REZdNXSQuBVp7PLOXOf5K9GgUJ-NiQR5vdEpisT8z7c4zJCGRLZsf6fId4ZBJTOiDY-Xo58bmUA_oQdUdWp9EKCCj_619rKHjcm9rihupEDDx2KClV7PxYlO2Ge4D0jmTJ79zK0ZGJgX7ZbjmCVPMbWoOe1lJ4dpjN5erMDh1obhW8SqUjCiq8Rp72leACDC74WjawWSEyQH0gaewcD2ipglPRWokT678WDc3X62G_sebRg3_TFVRCFZ9RXWFWbvfoegjd_Noam-65RciQmoWy1NX5LG_wMi-FoZCZE9P2YyPvtWM-XbYdmDUDLkBZmx0BteqGG-grMIRfBvnUaBKuuXhwIpK_B_OCMNb9jJ4m2uzLdfoFlZDERJqiQnlPbFbzhWd6tMrxmeWPW1JluWKHXpiNkihkTsnKjqpWzCv8Lesl45P0p3_1um59p8YvxP1C0LUrSMjO0ZUYwgVLIplmPTzoRneCT7Tei6BoDPkaR110VUmnhJnORr81XcB9qL0HDxLTOf1Np5s5KmMkCnilqoa6lG7EQR8NK6kMlue__9veJQJYyouFzg4w6dQuariFDEUBDnwHtYAoITGLxcVk7MemAp0hKCyQQRT4C1wvSO-GuJftYUdxqJAJkSFuBi0pKAfyqqt_BOpP0JYL6g=w454-h766-no)

## Donations

This software is completely free, licensed under the Apache 2.0 license. However, if you feel like you wish to donate some money to me, feel free to send any amount of money through Paypal to `gustav@gustav.dev`.
