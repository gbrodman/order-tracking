class Email:

  def __init__(self, address):
    self.email_address = address

  def to_row(self) -> list:
    return [self.email_address]

  def get_header(self) -> list:
    return ["Email Address"]


def from_row(header, row) -> Email:
  address = row[header.index("Email Address")]
  return Email(address)
