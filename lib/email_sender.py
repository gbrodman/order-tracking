import collections
import datetime
import smtplib
from email.mime.text import MIMEText

TODAY = datetime.datetime.now().strftime("%Y-%m-%d")


class EmailSender:

  def __init__(self, email_config) -> None:
    self.email_config = email_config

  def send_email(self, groups_dict) -> None:
    email_content = self.create_email_content(groups_dict)
    self.send_email_content("Tracking Numbers " + TODAY, email_content)

  def create_email_content(self, trackings) -> str:
    groups_dict = collections.defaultdict(list)
    for tracking in trackings:
      groups_dict[tracking.group].append(tracking)

    content = "Tracking number / order number(s) per group:\n\n"
    for group, trackings in groups_dict.items():
      numbers = [
          tracking.tracking_number + " / " + ", ".join(tracking.order_ids) +
          " / " + tracking.to_email for tracking in trackings
      ]
      content += f"{group} ({len(numbers)}):\n"
      content += '\n'.join(numbers)
      content += '\n\n'

    content += "These are tracking numbers we found based on unread emails. Some may have been found in the past."
    return content

  def send_email_content(self, subject, content, recipient=None) -> None:
    recipient = recipient if recipient else self.email_config['username']
    s = smtplib.SMTP(self.email_config['smtpUrl'],
                     self.email_config['smtpPort'])
    s.starttls()
    s.login(self.email_config['username'], self.email_config['password'])

    message = MIMEText(content)
    message['From'] = self.email_config['username']
    message['To'] = recipient
    message['Subject'] = subject
    s.sendmail(self.email_config['username'], recipient, message.as_string())
    s.quit()
