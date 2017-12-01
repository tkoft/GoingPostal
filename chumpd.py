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
import email


# document things, etc. - see API design doc.
# using pipenv; use `pipenv run python imap.py` to test, I think
# separate SMTP/IMAP stuff - different INIs for different emails
# use python 3! find an ide for this...
# try POP for some things?
# use UID command when possible...
# TODO: poll, send/receive on interval
# gmail policy: don't check IMAP more than once/10min.
# May need to IDLE - would using the 'recent' method help?


# The main command-line interface.
# Example usage: pipenv run python3 imap.py test.ini ~/test.sock
# Then invoke with: zerorpc -j ipc://$HOME/test.run recv
def main():
    parser = ArgumentParser()
    cfg = ConfigParser()
    parser.add_argument('config',
        help="INI file containing IMAP/SMTP configuration")
    parser.add_argument("socket",
        help="Location of socket to listen on")
    args = vars(parser.parse_args())
    config = args['config']

    s = zerorpc.Server(ChumpServer(config))
    s.bind("ipc://" + args['socket'])
    s.run()

# Tests.
# Example: pipenv run python3 -m unittest chumpd.py
class BasicTest(TestCase):
    def test_imap(self):
        with ChumpServer('test.ini') as server:
            print(server.recv())
            server.send('gonepostal003@gmail.com', 'ABC')
            server.send('gonepostal003@gmail.com', 'DEF')
            sleep(1)
            print(server.recv())


# The main server object
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
            smtp.starttls()
            smtp.login(self.config['smtp']['user'], self.config['smtp']['password'])
            self._smtp = smtp
        return self._smtp
    def get_imap(self):
        if self._imap is None:
            imap = IMAP4_SSL(self.config['imap']['server'], self.config['imap']['port'])
            # print(imap.capabilities)
            imap.authenticate('PLAIN', lambda resp:
                "{0}\x00{0}\x00{1}".format(self.config['imap']['user'], self.config['imap']['password']).encode()
            )
            self._imap = imap
        return self._imap
    def send(self, recipient, message): # 
        smtp = self.get_smtp()
        smtp.verify(self.config['smtp']['from'])
        msg = EmailMessage()
        msg['From'] = '<' + self.config['smtp']['from'] + '>'
        msg['To'] = recipient
        msg.set_content(message)
        smtp.send_message(msg)
    def recv(self):
        # Use 'UID' command whenever possible.
        # RECENT internally does a NOP just to get a reaction
        # We can use \\Recent to ensure that no one else has seen!
        imap = self.get_imap()
        imap.select()
        # could use SEARCH to narrow this down (or THREAD)
        typ, data = imap.fetch('1:*', '(RFC822)')
        data = [ email.message_from_string(x[1].decode())
            for x in data
            if isinstance(x, tuple) ]
        imap.store('1:*', '+FLAGS.SILENT', '\\Deleted')
        imap.expunge()
        imap.close()
        # https://stackoverflow.com/questions/45124127/
        return [x.get_payload() for x in data]
    # For 'with' statement to work:
    def __enter__(self):
        return self
    def __exit__(self, type, value, tb):
        if self._smtp is not None:
            self._smtp.quit()
        if self._imap is not None:
            self._imap.logout()

# Make "main" well-behaved.
# See: https://stackoverflow.com/questions/1590608/
if __name__=="__main__":
   main()