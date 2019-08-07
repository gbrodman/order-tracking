# order-tracking

This is a set of Python scripts that retrieves unread Amazon shipping notification emails, parses out the tracking number and other information from those emails, and (if configured) automatically uploads those tracking numbers to Pointsmaker, MYS, or USA buying groups, as appropriate. Regardless of uploading, it will group the tracking numbers by buying group and email them to you, for your own verification, tracking, or to upload to other buying groups. 

## Instructions (basic)

- `pip3 install pyyaml selenium`
- Copy config.yml.template to config.yml
- Fill in the values for your email, password, and buying group info. It will likely require some manipulation, and relies on having a separate folder for Amazon emails. For GMail, you should use an application-specific password. 
- Run `python3 get_tracking_numbers.py` and it should work assuing the config file is filled out correctly.
