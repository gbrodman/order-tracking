import pickle
import os.path
import imaplib
import re

OUTPUT_FOLDER = "output"
COSTS_FILE = OUTPUT_FOLDER + "/expected_costs.pickle"


class ExpectedCosts:

  def __init__(self, config):
    self.email_config = config['email']
    self.costs_dict = self.load_dict()

  def flush(self):
    if not os.path.exists(OUTPUT_FOLDER):
      os.mkdir(OUTPUT_FOLDER)

    with open(COSTS_FILE, 'wb') as stream:
      pickle.dump(self.costs_dict, stream)

  def load_dict(self):
    if not os.path.exists(COSTS_FILE):
      return {}

    with open(COSTS_FILE, 'rb') as stream:
      return pickle.load(stream)

  def get_expected_cost(self, order_id):
    if order_id not in self.costs_dict:
      costs_dict[order_id] = self.load_order_total(order_id)
      self.flush()
    return self.costs_dict[order_id]

  def load_order_total(self, order_id):
    mail = imaplib.IMAP4_SSL(self.email_config['imapUrl'])
    mail.login(self.email_config['username'], self.email_config['password'])
    mail.select('"[Gmail]/All Mail"')

    status, search_result = mail.uid('SEARCH', None,
                                     'FROM "auto-confirm@amazon.com"',
                                     'BODY "%s"' % order_id)
    email_id = search_result[0]

    result, data = mail.uid("FETCH", email_id, "(RFC822)")

    regex = r'Order Total: \$(\d+\.\d{2})'
    raw_email = str(data[0][1])
    order_total = max([float(cost) for cost in re.findall(regex, raw_email)])
    return order_total
