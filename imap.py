from imaplib import IMAP4_SSL
from datetime import datetime
from smtplib import SMTP_SSL, SMTP
from email.message import EmailMessage
from argparse import ArgumentParser
from configparser import ConfigParser
import zerorpc
import os
from unittest import TestCase
from time import sleep

# using pipenv; use `pipenv run python imap.py` to test, I think
# `zerorpc -j ipc:///home/work/test.run send` eg.

# currently broken :(

# add unit tests, etc...
# use python 3! find an ide for this...
# try POP for some things?

# use UID command when possible...

# gmail policy:
#  If your mail app checks for new messages more than once every 10
# minutes, the app’s access to your account could be blocked.
# May need to IDLE

# test wiht:
# pipenv run python -m unittest imap.py


config = None

def main():
    # homedir = os.path.expanduser('~') # https://stackoverflow.com/questions/10170407/
    parser = ArgumentParser()
    cfg = ConfigParser()
    parser.add_argument('config',
        help="INI file containing IMAP/SMTP configuration"
    )
    parser.add_argument("socket",
        help="Location of socket to listen on")
    args = vars(parser.parse_args())
    config = args['config']

    s = zerorpc.Server(ChumpServer(config))
    s.bind("ipc://" + args['socket'])
    s.run()

    

class ChumpServer:
    def __init__(self, config_file):
        self.config = ConfigParser()
        self.config.read(config_file)
        self._smtp = None
        self._imap = None
    def get_smtp(self):
        if self._smtp is None:
            smtp = SMTP(self.config['smtp']['server'], self.config['smtp']['port'])
            smtp.ehlo()
            print(smtp.starttls())
            print(smtp.login(self.config['smtp']['user'], self.config['smtp']['password']))
            self._smtp = smtp
        return self._smtp
    def get_imap(self):
        if self._imap is None:
            imap = IMAP4_SSL(self.config['imap']['server'], self.config['imap']['port'])
            print('Connected with capabilities: ')
            print(imap.capabilities)
            print(imap.authenticate('PLAIN', lambda resp:
                # temporarily hardcoding this....
                "{0}\x00{0}\x00{1}".format('gonepostal003@gmail.com', 'thisisnotsecret').encode()
            ))
            self._imap = imap
        return self._imap
    def send(self, recipient): # 
        smtp = self.get_smtp()
        print(smtp.verify(self.config['smtp']['from']))
        msg = EmailMessage()
        msg['From'] = '<' + self.config['smtp']['from'] + '>'
        msg['To'] = recipient
        msg.set_content('Hello world!')
        print(smtp.send_message(msg))
    def recv(self): # BROKEN!
        imap = self.get_imap()
        print(imap.select())
        typ, data = imap.search(None, 'ALL')
        print(data)
        imap.close()
        return data
    def __enter__(self):
        return self
    def __exit__(self, type, value, tb):
        if self._smtp is not None:
            self._smtp.quit()
        if self._imap is not None:
            self._imap.logout()
            # should pass flags as r'(\Deleted)` eg.
        # may want to use 'Referecnes' header
        #  https://stackoverflow.com/questions/7310003/search-imap-using-parsed-date-from-another-email

#  pipenv run python -m unittest imap.py
class BasicTest(TestCase):
    def test_imap(self):
        with ChumpServer('test.ini') as server:
            server.recv()
            server.send('gonepostal003@gmail.com')
            sleep(1)
            server.recv()




# https://stackoverflow.com/questions/1590608/
if __name__=="__main__":
   main()

# run: python3 imap.py
# today = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")
# get a proper ide for this
#     res = M.append('INBOX', r'(\Flagged)', None, """
# From: <gonepostal001@gmail.com>
# Date: {date}
# """.format(date=today).encode())
    # print(res)