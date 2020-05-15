# config.py
#
# Open config file
#
import yaml

def open_config():
  with open( "config.yml", 'r') as config_file_stream:
    config = yaml.safe_load(config_file_stream)
  return config
