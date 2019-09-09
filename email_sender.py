import datetime
import smtplib
from email.mime.text import MIMEText

TODAY = datetime.datetime.now().strftime("%Y-%m-%d")


class EmailSender:

  def __init__(self, email_config):
    self.email_config = email_config

  def send_email(self, groups_dict):
    email_content = self.create_email_content(groups_dict)
    self.send_email_content("Tracking Numbers " + TODAY, email_content)

  def create_email_content(self, groups_dict):
    content = "Tracking number / order number(s) per group:\n\n"
    for group, trackings in groups_dict.items():
      numbers = [
          tracking.tracking_number + " / " + ", ".join(tracking.order_ids)
          for tracking in trackings
      ]
      content += group
      content += '\n'
      content += '\n'.join(numbers)
      content += '\n\n'

    content += "These are tracking numbers we found based on unread emails. Some may have been found in the past."
    return content

  def send_email_content(self, subject, content):
    s = smtplib.SMTP(self.email_config['smtpUrl'],
                     self.email_config['smtpPort'])
    s.starttls()
    s.login(self.email_config['username'], self.email_config['password'])

    message = MIMEText(content)
    message['From'] = self.email_config['username']
    message['To'] = self.email_config['username']
    message['Subject'] = subject
    s.sendmail(self.email_config['username'], self.email_config['username'],
               message.as_string())
    s.quit()
