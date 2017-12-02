from imaplib import IMAP4_SSL
from datetime import datetime
from smtplib import SMTP_SSL, SMTP
from email.message import EmailMessage
from argparse import ArgumentParser
from configparser import ConfigParser
from collections import defaultdict
import zerorpc
import os
from unittest import TestCase
from time import sleep
import re
import email

# fix zerorpc cli -  TODO unit test
# document things, etc. - see API design doc.
# using pipenv; use `pipenv run python imap.py` to test, I think
# separate SMTP/IMAP stuff - different INIs for different emails
# use python 3! find an ide for this...
# try POP for some things?
# use UID command when possible...
# TODO: poll, send/receive on interval
# gmail policy: don't check IMAP more than once/10min.
# May need to IDLE - would using the 'recent' method help?
# allowed "less secure apps" for google/yahoo
# for yahoo: had ot move emails out of spam


# The main command-line interface.
# Example usage: pipenv run python3 chumpd.py configs/gmail3.ini ~/test.sock
# Then invoke with: zerorpc -j ipc://$HOME/test.sock recv
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
        with ChumpServer('configs/gmail3.ini') as gmail3, \
            ChumpServer('configs/gmail2.ini') as gmail2, \
            ChumpServer('configs/yahoo1.ini') as yahoo1:
            print(yahoo1.recv('app'))
            print(gmail3.recv('app'))
            gmail2.send('app', [gmail3.get_addr(), yahoo1], 'ABC')
            gmail2.send('app', gmail3.get_addr(), 'DEF')
            gmail2.send('app', yahoo1.get_addr(), 'DEF')
            sleep(2)
            print(gmail3.recv('app'))
            print(yahoo1.recv('app'))


# The main server object
class ChumpServer:
    def __init__(self, config_file):
        self.config = ConfigParser()
        self.config.read(config_file)
        self._smtp = None
        self._imap = None
        self.queues = defaultdict(dict)
        self.doomed = []
    def get_addr(self):
        return self.config['email']['address']
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
            # print("Connecting to {0}...".format(self.config['imap']['server']))
            # print(imap.capabilities)
            # imap.login(self.config['imap']['user'], self.config['imap']['password'])
            imap.authenticate('PLAIN', lambda resp:
                "{0}\x00{0}\x00{1}".format(self.config['imap']['user'], self.config['imap']['password']).encode()
            )
            self._imap = imap
        return self._imap
    def send(self, key, recipient, message): # 
        if not isinstance(recipient, list):
            recipient = [recipient]
        recipient = [ x.get_addr()
            if isinstance(x, ChumpServer)
            else x
            for x in recipient ]
        smtp = self.get_smtp()
        smtp.verify(self.config['smtp']['from'])
        msg = EmailMessage()
        msg['From'] = '<' + self.config['smtp']['from'] + '>'
        msg['To'] = ', '.join(recipient)
        msg['Subject'] = key
        msg.set_content(message)
        smtp.send_message(msg)
        # TODO: error handling
    def sync(self):
        # Use 'UID' command whenever possible.
        # RECENT internally does a NOP just to get a reaction
        # We can use \\Recent to ensure that no one else has seen!
        imap = self.get_imap()
        typ, count = imap.select()
        count = count[0].decode()
        if count == '0':
            return []
        # could use SEARCH to narrow this down (or THREAD)
        typ, data = imap.fetch('1:*', '(UID RFC822)')
        # print(data)
        messages = [ x
            for x in data
            if isinstance(x, tuple) ]
        for (mkey, mvalue) in messages:
            message = email.message_from_string(mvalue.decode())
            frm = message['From']
            uid = re.search(rb'UID\s*(\d+)', mkey).group(1).decode()
            subj = message['Subject']
            body = message.get_payload()
            # print('MSG: {0} {1} {2}'.format(uid, subj, body))
            self.queues[subj][uid] = (frm, body)
    def doom(self):
        imap = self.get_imap()
        if len(self.doomed) > 0:
            doomed = ','.join(self.doomed)
            imap.uid("STORE", doomed, '+FLAGS', '\\Deleted')
            imap.expunge()
            self.doomed = []
    def recv(self, key):
        self.sync()
        ret = []
        print('here')
        for uid, (frm, body) in self.queues[key].items():
            self.doomed.append(uid)
            ret.append([frm, body])
        self.doom()
        print(ret)
        return ret
        # imap.store('1:*', '+FLAGS.SILENT', '\\Deleted')
        # imap.expunge()
        # https://stackoverflow.com/questions/45124127/
        # return [x.get_payload() for x in data]
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