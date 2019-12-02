# Order Tracking

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

## Limitations

- This will only work for one email account at a time
- This will only work for GMail
- Auto-uploading only works for USA and sites whose websites are of the same format as Pointsmaker or MYS
- All addresses must contain a key that uniquely identifies which buying group the address belongs to. The default is a part of the group's address.

## Prerequisites

- Python3 and pip3 (these should come together)

## Instructions

**If you are on Windows, use [this guide](https://docs.google.com/document/d/1wivg69Urc9boScOUvW4sdP6zJrayikNyzKcJgS2kjyw/edit#heading=h.k3xoxdnm2imr) instead of these instructions, as Windows is a bit difficult and this guide is clear.**

### If you are on a Mac (OSX):
Open up a terminal and run the following commands. These install Homebrew (a package manager), then they use Homebrew to install Git+Python, download the project, then set up the Python environment.


```
cd ~
/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
brew install pyenv
brew install git
git clone https://github.com/gbrodman/order-tracking.git
cd order-tracking
pyenv install 3.7.4
pyenv global 3.7.4
echo -e 'if command -v pyenv 1>/dev/null 2>&1; then\n  eval "$(pyenv init -)"\nfi' >> ~/.bash_profile
source ~/.bash_profile
pip install -r requirements.txt
```

### In all operating systems:
- Disconnect from any VPNs that might interfere (they might or might not cause you some network connectivity issues)
- Enable IMAP in GMail--go to the Settings page, then the "Forwarding and POP/IMAP" tab, then make sure IMAP is enabled
- Copy config.yml.template to config.yml
- Set up the configuration (see the "Configuration" section below for more info)
- Run `python get_tracking_numbers.py` followed by `python reconcile.py`

## Configuration

Here are details of the fields on config.yml:

- The email and password should be a GMail account -- specifically, the password should be an [app-specific password](https://support.google.com/accounts/answer/185833?hl=en). You can likely keep the IMAP and SMTP configuration the same (unless you know for sure that you shouldn't).
- For each group in 'groups', include the full name of the group (for sites like MYS, this should be the URL minus the ".com" bit). Include a unique key per group (default is based on the address) that will appear only in shipping notifications to that group. The username and password should be to the group's online portal so that we can upload tracking numbers and scrape reconciliation data.
- lookbackDays is how far back in your email account we'll search for unread Amazon shipping emails. Note: the shipment links expire after 45 days so we shouldn't go past that
- The reconciliation baseSpreadsheetId should be the ID of an existing Google Sheet. See the section below on how to give correct permissions to that sheet. The ID can be retrieved form the URL, which is of the form "https://docs.google.com/spreadsheets/d/SHEET_ID"
- The "driveFolderId" field should be the ID of a Google Drive folder into which we will store persistent data. This can be retrieved from the URL of the folder, which is of the form "https://drive.google.com/drive/folders/FOLDER_ID"

### Sheets / Drive Configuration and Permissions

We need to create and use an automated Google Cloud account to write to Drive and to Sheets. Here's how we do that:

- First, create a Google Cloud project at https://console.cloud.google.com
- Next, create the serivce account in Google Cloud and get the credentials for it, by following steps 1-5 on [this page](https://docs.bmc.com/docs/PATROL4GoogleCloudPlatform/10/creating-a-service-account-key-in-the-google-cloud-platform-project-799095477.html). Make sure to note the email address of the service account -- it should be very long, and it should include ".gserviceaccount.com" at the end.
- When you download the credentials JSON file, rename it "creds.json" and put it in the same directory as these scripts.
- In the Google Cloud console website, use the left navigation pane to go to "APIs and Services"
- Next, click "Enable APIs and Services". This will take you to the API library. You need to search for and enable the "Google Drive API" and "Google Sheets API". For each, search for it, click the term, and enable it.
- Next, for the reconciliation Google Sheet and the Google Drive folder that we set up, make sure to share the sheet/folder with the service account that we created before. Just share them both with the email address that ends in ".gserviceaccount.com" (make sure the address has editing permissions on the sheet and folder).

That should be it -- the "creds.json" file will give the scripts the ability to run as the service account, and we've given the service account permissions to the things it needs to write to.

## Arguments

- `--no-headless` to run in a standard browser, rather than a headless browser. This is useful if you want to see what the Selenium browser automation is actually doing.
- `--firefox` to run using Firefox/Geckodriver rather than Chrome
- `--groups A B` will only run reconciliation over groups A and B. If omitted, will run over all groups.

## Sheets Output

The reconciliation task has output that consists of two tabs in the Google Sheet that we configured earlier. The tabs are:

### Reconciliation

This is the main spreadsheet. Because a single tracking number can consist of multiple orders and a single order can contain multiple tracking numbers, we group them into orders based on how the shipments were divided up. The columns are:

- Orders: Order IDs contained in this group
- Trackings: Tracking numbers contained in this group
- Amount Billed: Total amount that you were charged for this group
- Amount Reimbursed: Total amount that the buying groups' sites show for this group
- Last Ship Date: This is the date of the most recent shipment. If it was long ago and the order is under-reimbursed, you probably have a problem.
- POs: List of purchase orders (currently only for USA)
- Group: the buying group
- To Email: the email to which the shipping/order emails were sent
- Manual Cost Adjustment: This is a way to adjust the expected reimbursed cost for an order. If you know that an item was under-reimbursed for a good reason, you can add that amount here. We expect that the amount billed is equal to the amount reimbursed plus this manual cost adjustment. This is saved if you change it.
- Manual Override: Another manual field, check this if you're sure that the group looks correct -- it will ignore anything else and mark as resolved
- Total Diff: This is the total difference between amount billed and reimbursed (plus manual adjustments). Green means that the amounts were equal or the override was checked, yellow means you were over-reimbursed, and red means you were under-reimbursed.
- Notes: Notes for your own personal use

### Trackings

Each row on this sheet corresponds to a tracking number. It contains order(s) for that tracking and other information about it, including the reimbursed amount if we could find one. This tab is most useful in figuring out exactly where a problem occurred, if a group has mis-scanned some item.

## Amazon Report Import

TODO

## Manual Order Import

TODO

## Donations

This software is completely free, licensed under the GNU Affero General Public License. However, if you feel like you wish to donate some money to me, feel free to send any amount of money through Paypal to https://paypal.me/GustavBrodman
