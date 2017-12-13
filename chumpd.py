# CHUMPD (server for the Chen-Hansel Ulterior Messaging Protocol)
# Exposes a zerorpc API for building social media applications over email.
# Why? Because we can, that's why.

from imaplib import IMAP4_SSL
from datetime import datetime
from smtplib import SMTP_SSL, SMTP, SMTPServerDisconnected
from email.message import EmailMessage
from argparse import ArgumentParser
from configparser import ConfigParser
from collections import defaultdict
import zerorpc
import os
from unittest import TestCase
from time import sleep
import re
import base64
import email

# - Note to self: use VS Code for autocomplete
# - gmail policy: don't check IMAP more than once/10min.
# - May need to IDLE - would using the 'recent' method help?
# - allowed "less secure apps" for google/yahoo; disabled spam filters

# The main command-line interface.
# Example usage: pipenv run python3 chumpd.py configs/gmail3.ini ipc://$HOME/test.sock
# Then test with: zerorpc ipc://$HOME/test.sock recv app
def main():
    parser = ArgumentParser()
    cfg = ConfigParser()
    parser.add_argument('config',
        help="INI file containing IMAP/SMTP configuration")
    parser.add_argument("socket",
        help="Location of socket to listen on (e.g. ipc://$HOME/test.sock)")
    args = vars(parser.parse_args())
    config = args['config']

    s = zerorpc.Server(ChumpServer(config))
    s.bind(args['socket'])
    s.run()

# Tests.
# Example: pipenv run python3 -m unittest chumpd.py
# TODO: write tests for CLI
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
# TODO: error handling
class ChumpServer:
    def __init__(self, config_file):
        self._config = ConfigParser()
        self._config.read(config_file)
        self._smtp = None
        self._imap = None
        self._queues = defaultdict(dict)
        self._doomed = []
    def get_addr(self):
        return self._config['email']['address']
    def get_smtp(self):
        if self._smtp is None:
            smtp_config = self._config['smtp']
            smtp = SMTP(smtp_config['server'], smtp_config['port'])
            smtp.ehlo()
            smtp.starttls()
            smtp.login(smtp_config['user'], smtp_config['password'])
            self._smtp = smtp
        try:
            self._smtp.verify(self._config['smtp']['from'])
        except SMTPServerDisconnected:
            self._smtp = None
            return self.get_smtp()
        return self._smtp
    def get_imap(self):
        if self._imap is None:
            imap_config = self._config['imap']
            imap = IMAP4_SSL(imap_config['server'], imap_config['port'])
            # print("Connecting to {0}...".format(self.config['imap']['server']))
            # print(imap.capabilities)
            imap.authenticate('PLAIN', lambda resp:
                "{0}\x00{0}\x00{1}".format(imap_config['user'], imap_config['password']).encode()
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
        
        msg = EmailMessage()
        msg['From'] = '<' + self._config['smtp']['from'] + '>'
        msg['To'] = ', '.join(recipient)
        msg['Subject'] = base64.a85encode(str.encode(key)).decode()
        msg.set_content(base64.a85encode(str.encode(message),wrapcol=80).decode())
        smtp.send_message(msg)
    # TODO: poll, send/receive on interval
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
            sender = message['From']
            uid = re.search(rb'UID\s*(\d+)', mkey).group(1).decode()
            # print('MSG: {0} {1} {2}'.format(uid, message['Subject'], message.get_payload()))
            try:
                subj = base64.a85decode(message['Subject']).decode()
                # https://stackoverflow.com/questions/45124127/
                body = base64.a85decode(message.get_payload()).decode()
                self._queues[subj][uid] = (sender, body)
            except:
                pass
                # self._doomed.append(uid) <- in future
                # print('Message in old format!')
                # Do nothing - this isn't a CHUMP message
    def doom(self):
        imap = self.get_imap()
        if len(self._doomed) > 0:
            doomed = ','.join(self._doomed)
            imap.uid("STORE", doomed, '+FLAGS', '\\Deleted')
            imap.expunge()
            self._doomed = []
    def recv(self, key):
        self.sync()
        ret = []    
        for uid, (sender, body) in self._queues[key].items():
            self._doomed.append(uid)
            ret.append(dict(sender=sender,body=body))
        self.doom()
        self._queues[key] = {}
        return ret

    def store(self, key, message):
        keyEncoded = base64.a85encode(str.encode(key)).decode()
        messageEncoded = base64.a85encode(str.encode(message),wrapcol=80).decode()

        imap = self.get_imap();
        resp, data = imap.list('""', '*Draft*')
        draftsBoxName = data[0].split()[3];
        typ, count = imap.select(draftsBoxName);

        # Delete old draft if it exists
        typ, msgnums = imap.search(None, '(SUBJECT "' + keyEncoded + '")')
        if len(msgnums) > 0:
            for num in msgnums[0].split():
                imap.store(num, '+FLAGS', '\\Deleted')
        imap.expunge()

        msg = email.message.Message()
        msg['Subject'] = keyEncoded
        # Some servers are picky abour CRLF at the end of messages
        messageEncoded += "\r\n"
        msg.set_payload(messageEncoded)
        typ, resp = imap.append(draftsBoxName, None, None, str(msg).encode())
    
    def retrieve(self, key):
        keyEncoded = base64.a85encode(str.encode(key)).decode()

        imap = self.get_imap();
        resp, data = imap.list('""', '*Draft*')
        draftsBoxName = data[0].split()[3];
        typ, count = imap.select(draftsBoxName);
        typ, msgnums = imap.search(None, '(SUBJECT "' + keyEncoded + '")')

        if count == '0' or len(msgnums) == 0 or typ == "NO":
            return '';

        typ, data = imap.fetch(msgnums[0].split()[0], '(RFC822)')
        mkey, mvalue = data[0]
        message = email.message_from_string(mvalue.decode())
        return base64.a85decode(message.get_payload()).decode()


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