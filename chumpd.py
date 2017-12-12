# CHUMPD (server for the Chen-Hansel Ulterior Messaging Protocol)
# Exposes a zerorpc API for building social media applications over email.
# Why? Because we can, that's why.

import gi
# TODO: make sure everything works via env variables, no ext. dependencies
gi.require_version('Nice', '0.1')
from imaplib import IMAP4_SSL
from datetime import datetime
from smtplib import SMTP_SSL, SMTP, SMTPServerDisconnected
from email.message import EmailMessage
from argparse import ArgumentParser
from configparser import ConfigParser
from collections import defaultdict
from gi.repository import Nice, GObject, GLib
from threading import Thread
import msgpack

# GObject.threads_init() <- no longer necessary
print(dir(Nice))
# A NiceAgent must always be used with a GMainLoop running the GMainContext passed into nice_agent_new() (or nice_agent_new_reliable()). Without the GMainContext being iterated, the agent’s timers will not fire, etc.
# ISSUE: yahoo doesnt seem to be expunging properly
# I think I fixed ctl-c; todo cleanup suspended procs.


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
    def test_tcp(self):
        with ChumpServer('configs/gmail3.ini') as gmail3, \
            ChumpServer('configs/gmail2.ini') as gmail2:
            print('Starting...')
            gmail2.send('app', gmail3, 'M1')
            sleep(1)
            print(gmail3.recv('app'))
            gmail2.send('app', gmail3, 'M2')
            sleep(1)
            print(gmail3.recv('app'))
            gmail2.send('app', gmail3, 'M3')
            sleep(1)
            print(gmail3.recv('app'))
    # def test_imap(self):
    #     with ChumpServer('configs/gmail3.ini') as gmail3, \
    #         ChumpServer('configs/gmail2.ini') as gmail2, \
    #         ChumpServer('configs/yahoo1.ini') as yahoo1:
    #         # Test 'recv'
    #         yahoo1.recv('app')
    #         gmail3.recv('app')
    #         self.assertEqual(yahoo1.recv('app'), [], 'Yahoo is empty')
    #         self.assertEqual(gmail3.recv('app'), [], 'Gmail is empty')
    #         gmail2.send('app', [gmail3.get_addr(), yahoo1], 'ABC')
    #         gmail2.send('app', gmail3.get_addr(), 'DEF')
    #         gmail2.send('app', yahoo1.get_addr(), 'DEF')
    #         sleep(2)
    #         rec1 = gmail3.recv('app')
    #         rec2 = yahoo1.recv('app')
    #         expected = [
    #             dict(sender='gonepostal002@gmail.com', body='ABC'),
    #             dict(sender='gonepostal002@gmail.com', body='DEF')
    #         ]
    #         self.assertCountEqual(rec1, expected, 'Gmail3 works')
    #         self.assertCountEqual(rec2, expected, 'Yahoo1 works')


class NiceThread(Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.context = GLib.MainContext.new()
        self.daemon = True
    def run(self):
        GLib.MainLoop.new(self.context, False).run()

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
        self._tcp_off = {}
        self._tcp_conn = {}
        self._nice_thread = NiceThread()
        self._nice_thread.start()
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
    def setup_tcp(self, recipient):
        Nice.NiceAgent.new(self._nice_thread.context, Nice.Compatibility.RFC5245)
    def send(self, key, recipients, message): #
        if not isinstance(recipients, list):
            recipients = [recipients]
        recipients = [ x.get_addr()
            if isinstance(x, ChumpServer)
            else x
            for x in recipients ]
        smtp = self.get_smtp()
        full_message = {
            'sender': self._config['email']['address'],
            'body': message
        }
        for r in recipients:
            if r in self._tcp_conn:
                print('HAVE CONNECTION!')
            elif r in self._tcp_off:
                full_message['offfer'] = self._tcp_off[r]
            else:
                # prepare for TCP, but we won't hav ean offer available yet
                # should we *block* here in case an offer becomes available?
                self.setup_tcp(r)
        msg = EmailMessage()
        msg['From'] = '<' + self._config['smtp']['from'] + '>'
        msg['To'] = ', '.join(recipient)
        msg['Subject'] = base64.a85encode(str.encode(key)).decode()
        msg.set_content(base64.a85encode(msgpack.packb(full_message),wrapcol=80).decode())
        smtp.send_message(msg)

    # TODO: poll, send/receive on interval
    # TODO: make methods private
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
        print('fetch starting')
        typ, data = imap.fetch('1:*', '(UID RFC822)')
        print('fetch over')
        # print(data)
        messages = [ x
            for x in data
            if isinstance(x, tuple) ]
        for (mkey, mvalue) in messages:
            message = email.message_from_string(mvalue.decode())
            uid = re.search(rb'UID\s*(\d+)', mkey).group(1).decode()
            # print('MSG: {0} {1} {2}'.format(uid, message['Subject'], message.get_payload()))
            try:
                subj = base64.a85decode(message['Subject']).decode()
                # https://stackoverflow.com/questions/45124127/
                full_message = msgpack.unpackb(base64.a85decode(message.get_payload()), encoding='utf-8')
                print(full_message)
                self._queues[subj][uid] = full_message
            except:
                # Just ignore malformed messages
                pass
                # self._doomed.append(uid) <- in future
                # print('Message in old format!')
                # Do nothing - this isn't a CHUMP message
    def doom(self):
        imap = self.get_imap()
        if len(self._doomed) > 0:
            doomed = ','.join(self._doomed)
            print('Dooming: ', doomed)
            print(imap.uid("STORE", doomed, '+FLAGS', '\\Deleted'))
            print(imap.expunge())
            self._doomed = []
    def recv(self, key):
        self.sync()
        ret = []
        for uid, full_message in self._queues[key].items():
            self._doomed.append(uid)
            ret.append(dict(sender=full_message['sender'],body=full_message['body']))
        self.doom()
        self._queues[key] = {}
        return ret
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