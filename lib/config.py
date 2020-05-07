# config.py
#
# Open config file
#
import yaml

def open_config():
  CONFIG_FILE = "config.yml"
  with open(CONFIG_FILE, 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)
  return config
