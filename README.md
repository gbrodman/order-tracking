# order-tracking

## Instructions (basic)

- `pip3 install pyyaml selenium`
- Copy config.yml.template to config.yml
- Fill in the values for your email, password, and buying group info. It will likely require some manipulation, and relies on having a separate folder for Amazon emails. For GMail, you should use an application-specific password. 
- Run `python3 get_tracking_numbers.py` and it should work assuing the config file is filled out correctly.
