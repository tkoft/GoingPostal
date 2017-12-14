# CHUMPD (server for the Chen-Hansel Ulterior Messaging Protocol)
# Exposes a zerorpc API for building social media applications over email.
# Why? Because we can, that's why.

import gi
gi.require_version('Nice', '0.1')
from imaplib import IMAP4_SSL
from datetime import datetime
from smtplib import SMTP_SSL, SMTP, SMTPServerDisconnected
from email.message import EmailMessage
from argparse import ArgumentParser
from configparser import ConfigParser
from collections import defaultdict
from gi.repository import Nice, GLib
from threading import Thread, Lock, Timer, Event
from queue import Queue, Empty
import msgpack
import zerorpc
from typing import Callable
import os
from unittest import TestCase
from time import sleep, time
import re
import base64
import email
import collections
from operator import itemgetter, attrgetter
import struct
from tcp_support import TcpDictionary


# push asap once I unbreak things
# TODO: make methods private
# FIXME: cf checlist
# FIXME: broke recv from email?
# FIXME: Gary having issues with multiple recv's
# FIXME: current issue -- sending works but recv doesn't; check both directions
# TODO: try UDP instead?
# TODO: test TCP with multicasting, NATs (use STUN)
# TODO: see powerpoint and things we gave to Jeannie
# TODO: TCP is unreliable, slow; get it working with CrapChat.
# TODO make sleep and verbosity configurable
# FIXME: n2s: can't 'send to yourself' over tcp
# TODO: m3d/m3e below sometimes fails; maybe hooking wrong event on agent for detecting complete connection
# TODO: write tests for CLI, and various special cases; speed up testing
# TODO: make build/setup easy
# NOTE: allowed "less secure apps" for google/yahoo; disabled spam filters




# Tests.
# Example: pipenv run python3 -m unittest chumpd.py

# https://stackoverflow.com/questions/17330139/python-printing-a-dictionary-as-a-horizontal-table-with-headers
def printTable(myDict, colList=None):
   """ Pretty print a list of dictionaries (myDict) as a dynamically sized table.
   If column names (colList) aren't specified, they will show in random order.
   Author: Thierry Husson - Use it as you want but don't blame me.
   """
   if len(myDict) == 0:
       print('[ No messages ]')
       return
   if not colList: colList = list(myDict[0].keys() if myDict else [])
   myList = [colList] # 1st row = header
   for item in myDict: myList.append([str(item[col] if col in item else None) for col in colList])
   colSize = [max(map(len,col)) for col in zip(*myList)]
   formatStr = ' | '.join(["{{:<{}}}".format(i) for i in colSize])
   myList.insert(1, ['-' * i for i in colSize]) # Seperating line
   for item in myList: print(formatStr.format(*item))


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

class BasicTest(TestCase):
    def test_tcp(self):
        with ChumpServer('configs/gmail4.ini') as gmail4, \
            ChumpServer('configs/gmail1.ini') as gmail1:
            print('Starting...')
            gmail1.send('app', gmail4, 'M1')
            sleep(30)
            print('SHOULD SEND OFFER:')
            gmail1.send('app', gmail4, 'M2') # Send an offer
            sleep(10)
            print('SHOULD RECEIVE OFFER and SEND ANSWER:')
            printTable(gmail1.recv('app'))
            printTable(gmail4.recv('app'))
            sleep(80)
            print('SHOULD HAVE CONNECTION:')
            gmail1.send('app', gmail4, 'M3') # Connection established
            sleep(1)
            printTable(gmail4.recv('app'))  # recv over tcp
            gmail4.send('app', gmail1, 'M3B') # Connection established
            gmail4.send('app', gmail1, 'M3C') # Connection established
            sleep(30)
            printTable(gmail1.recv('app'))  # recv over tcp
            gmail1.send('app', gmail4, 'M3D') # Connection established
            gmail1.send('app', gmail4, 'M3E') # Connection established
            sleep(5)
            printTable(gmail4.recv('app'))  # recv over tcp

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



# The main server object



class RecvThread(Thread):

    def __init__(self, stop_event, chump):
        super().__init__(daemon=True)
        self.daemon = True
        self._stop_event = stop_event
        self._chump = chump
        self.doomed = Queue()
    def log(self, *args):
        self._chump.log('recv_thread', *args)
    def run(self):
        while not self._stop_event.is_set():
            with self._chump.lock:
                self._doom()
                self._sync()
            sleep(15)
        self.log('DONE!')
    def _doom(self):
        to_doom = []
        while True:
            try:
                to_doom.append(self.doomed.get_nowait())
            except(Empty):
               break
        imap = self._chump.get_imap()
        if len(to_doom) > 0:
            doomed = ','.join(to_doom)
            imap.uid("STORE", doomed, '+FLAGS', '\\Deleted')
            # imap.uid("EXPUNGE", doomed)
            imap.expunge()
            to_doom = []
    def _sync(self):
        imap = self._chump.get_imap()
        typ, count = imap.select()
        count = count[0].decode()
        if count == '0':
            return
        typ, data = imap.fetch('1:*', '(UID RFC822)')
        messages = [ x
            for x in data
            if isinstance(x, tuple) ]
        offers = []
        for (mkey, mvalue) in messages:
            message = email.message_from_string(mvalue.decode())
            uid = re.search(rb'UID\s*(\d+)', mkey).group(1).decode()
            full_message = None
            try:
                # https://stackoverflow.com/questions/45124127/
                full_message = msgpack.unpackb(base64.a85decode(message.get_payload()), encoding='utf-8')
            except:
                # Just ignore seriously malformed messages
                pass
            if full_message is not None and 'key' in full_message:
                if full_message['key'] == '__answer':
                    self._chump.tcpdict[full_message['sender']].got_answer(full_message['body'])
                    self.doomed.put(uid)
                else:
                    self._chump.queues[full_message['key']][uid] = full_message
                    if 'offer' in full_message:
                        offers.append(full_message)
        for offer in offers:
            self.log(f'Got offer')
            self._chump.tcpdict[offer['sender']].got_offer(offer['offer'])
            offer['offer'] = 'X'

class ChumpServer:
    def log(self, *args):
        if self._verbose:
            print(f'[{self.get_addr()}]', *args)

    def __init__(self, config_file):
        self._verbose = True
        self._config = ConfigParser()
        self._config.read(config_file)
        self._smtp = None
        self._imap = None
        self.queues = defaultdict(dict)
        self.tcpdict_messages = defaultdict(list)
        self.tcpdict = TcpDictionary(self)
        self.lock = Lock() # Lock for imap, _tcp, queues
        self._stop_event = Event()
        self._recv_thread = RecvThread(self._stop_event, self)
        self._recv_thread.start()

    def get_addr(self):
        return self._config['email']['address']
    def _get_smtp(self):
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
            return self._get_smtp()
        return self._smtp
    def get_imap(self):
        if self._imap is None:
            imap_config = self._config['imap']
            imap = IMAP4_SSL(imap_config['server'], imap_config['port'])
            imap.authenticate('PLAIN', lambda resp:
                "{0}\x00{0}\x00{1}".format(imap_config['user'], imap_config['password']).encode()
            )
            self._imap = imap
        return self._imap
    def _send_email(self, recipients, message):
        smtp = self._get_smtp()
        if len(recipients) > 0:
            msg = EmailMessage()
            msg['From'] = '<' + self._config['smtp']['from'] + '>'
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = 'CHUMP Message'
            msg.set_content(message)
            smtp.send_message(msg)

    def send(self, key, recipients, message):
        if not isinstance(recipients, list):
            recipients = [recipients]
        recipients = [ x.get_addr()
            if isinstance(x, ChumpServer)
            else x
            for x in recipients ]
        smtp = self._get_smtp()
        full_message = {
            'key': key,
            'sender': self._config['email']['address'],
            'body': message,
            'timestamp': int(time()),
            'protocol': 'email'
        }
        message_tcp = base64.a85encode(msgpack.packb(
             {**full_message, 'protocol': 'tcp'},
        use_bin_type=True)).decode()
        new_recipients = []
        with self.lock:
            for r in recipients:
                if not self.tcpdict[r].try_send(message_tcp):
                    offer = self.tcpdict[r].make_offer()
                    if offer is not None:

                        self.log(f'Providing offer... {full_message["timestamp"]}')
                        message_email = base64.a85encode(msgpack.packb(
                            {**full_message, 'offer': offer},
                        use_bin_type=True),wrapcol=80).decode()
                        self._send_email([r], message_email)
                    else:
                        new_recipients.append(r)
        message_email = base64.a85encode(msgpack.packb(
             full_message,
        use_bin_type=True),wrapcol=80).decode()
        self._send_email(new_recipients, message_email)


    def _send_answer(self, recipient, data, offer):
        self.log('Sending answer!')
        self.send('__answer', recipient, [offer, data])

    def recv(self, key):
        with self.lock:
            # NOTE: we assume here that the 'sender' value in each message is correct
            # (i.e. we allow the other users to spoof their own addresses). Since this
            # whole thing is insecure anyway, it doesn't matter much.

            # 1. Get items from each TCP connection:
            for k, val in self.tcpdict.items():
                for msg in val.read_messages():
                    self.tcpdict_messages[msg['key']].append(msg)
            mq = [x for x in self.tcpdict_messages[key]]
            self.tcpdict_messages[key] = []

            # 2. Get items from the receive thread's queue, and mark them for deletion:
            for uid, full_message in self.queues[key].items():
                self._recv_thread.doomed.put(uid)
                mq.append(full_message)
            self.queues[key] = {}

            # 3. Sort by timestamp so things are at least somewhat in order:
            mq.sort(key=
                lambda x: (x['timestamp'] if ('timestamp' in x) else 0)
            )
            return mq

    def store(self, key, message):
        keyEncoded = key;
        #keyEncoded = base64.a85encode(str.encode(key)).decode()
        messageEncoded = base64.a85encode(str.encode(message),wrapcol=80).decode()

        with self.lock:
            imap = self.get_imap();
            resp, data = imap.list('""', '*Draft*')
            draftsBoxName = data[0].split()[3];
            typ, count = imap.select(draftsBoxName);

            # Delete old draft if it exists
            typ, msgnums = imap.search(None, 'SUBJECT', keyEncoded)
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
        keyEncoded = key;
        with self.lock:
            imap = self.get_imap();
            resp, data = imap.list('""', '*Draft*')
            draftsBoxName = data[0].split()[3];
            typ, count = imap.select(draftsBoxName);
            typ, msgnums = imap.search(None, 'SUBJECT', keyEncoded)

            if count == '0' or len(msgnums[0]) == 0 or typ == "NO":
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
        self._stop_event.set()

# Make "main" well-behaved.
# See: https://stackoverflow.com/questions/1590608/
if __name__=="__main__":
   main()