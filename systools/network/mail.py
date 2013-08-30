import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging


logger = logging.getLogger(__name__)


class Email(object):

    def __init__(self, host, username, password, port):
        self.server = smtplib.SMTP(host, port)
        self.server.ehlo()
        self.server.starttls()
        self.server.ehlo()
        self.server.login(username, password)

    def send(self, from_addr, to_addr, subject, body, mime_type='plain'):
        msg = MIMEMultipart('alternative')
        msg['From'] = from_addr
        msg['To'] = to_addr
        msg['Subject'] = subject
        msg.attach(MIMEText(body, mime_type))
        text = msg.as_string()
        self.server.sendmail(from_addr, to_addr, text)
