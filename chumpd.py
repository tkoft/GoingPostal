# CHUMPD (server for the Chen-Hansel Ulterior Messaging Protocol)
# Exposes a zerorpc API for building social media applications over email.
# Why? Because we can, that's why.


# use 'pipenv run code' for mypy?

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

# note: you need pygobject working,
# and Sony Ericsson's openwebrtc installed; this has to be compiled with introspection.
# i'm using the latest version of this from git.
# see: https://github.com/EricssonResearch/openwebrtc/issues/394#issuecomment-218276247
    # TODO: poll, send/receive on interval
    # TODO: make methods private

# TODO: actually test this on separate devices, with a nat;
# will need to serialize ICE candidates
# - will I need to use `freeice` or similar?

# FIXME: doesn't actually do anything with stun/turn
# could use libnice directly via pygobject?
#  -- one issue: libnice itself auto gets local addrs
#  - could use: nice_agent_get_default_local_candidate ()

# which change to agent.h fixed stuff?

# FIXME: broke recv from email?
# WORKS!!!! RECEIVE SUCCEEDS!
# TO INTEGRATE WITH API, CLEANUP ETC
#  - sems to work *although* state goes to 5 sometimes???

# FIXME: not expunging on gmail either

# FIXME: current issue -- sending works but recv doesn't; check both directions
# maybe related to why I have to use 'recv' (ie attach_recv
# breaks, recv_messages also breaks...)idk
# also maybe try making things non-reliable again?
# FIXME: are we creating too many agents?

AgentInfo = collections.namedtuple('AgentInfo', 'agent stream')

# TODO: make sure everything works via env variables, no ext. dependencies


# FIXME: yahoo doesnt seem to be expunging properly
# FIXME: see tcp.py - need to test NAT
# FIXME: recv *sometimes* works - (why not always? TTL issue?)
# - Note to self: use VS Code for autocomplete
# - gmail policy: don't check IMAP more than once/10min.
# - May need to IDLE - would using the 'recent' method help?
# - allowed "less secure apps" for google/yahoo; disabled spam filters

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

# TODO: deduplicate TCPs so we don't hava emultiple overlapping negotations

# Tests.
# Example: pipenv run python3 -m unittest chumpd.py
# TODO: write tests for CLI, and various special cases; speed this up
class BasicTest(TestCase):
    def test_tcp(self):
        with ChumpServer('configs/gmail4.ini') as gmail4, \
            ChumpServer('configs/gmail1.ini') as gmail1:
            print('Starting...')
            gmail1.send('app', gmail4, 'M1')
            sleep(30)
            # FIXME: n2s: can't 'send to yourself' over tcp
            # sleep(30) # Try to get a candidate... should show 'Adding offer'
            print('SHOULD SEND OFFER:')
            gmail1.send('app', gmail4, 'M2') # Send an offer
            sleep(10)
            print('SHOULD RECEIVE OFFER and SEND ANSWER:')
            # TODO: beow recv prob pointles snow
            sleep(80)
            print('SHOULD HAVE CONNECTION:')
            gmail1.send('app', gmail4, 'M3') # Connection established
            sleep(1)
            printTable(gmail4.recv('app'))  # recv over tcp
            gmail4.send('app', gmail1, 'M3B') # Connection established
            gmail4.send('app', gmail1, 'M3C') # Connection established
            sleep(5)
            # TODO: below sometimes fails; maybe hooking wrong event on agent for detecting complete connection
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


class NiceThread(Thread):
    def __init__(self, context):
        super().__init__(daemon=True)
        self.daemon = True
        self.context = context
    def run(self):
        GLib.MainLoop.new(self.context, False).run()


# The main server object
# TODO: does libnice successfully handle large packets? eg doing fragmentation and checking length
# TODO: test TCP with multicast, multiple simultaneous connections, bidiretional
# TODO: error handling; see powerpoint and things we gave to Jeannie
# FIXME: I'm going to have serious issues with how 'recv' works
#  -- attach_recv is needed for stun and it isn't introspectable...
# TODO: send and receive successfully over TCP
#     ^ and *reliably* do so -- ti fails sometimes now with 'invalid answer'
#     ^ may want to increase stun-pacing-timer
#     - i think the main reliability issue is related to old offers not getting deleted. sort by timestamp?
# TODO: lint this (typecheck?), improve/automate tests...
# ...test TCP in apps; generally test TCP more.

# TODO: auto recv on a schedule to get eg __answer's
# FIXME: crash at end related to sorce ref count
# -- I'm guessing that this has somethng to do with nicethreads?
#    -> fixed with two changes to agent.h - which was necessary?
# TODO: still getting length race issue - tries to read incorrect length

class OneWayConnection:
    def _set_connected(self):
        self._connected = True
    def read_messages(self):
        while True:
            try:
                self._bytes += self._data.get_nowait()
            except(Empty):
               break
        print('READ: ', self._bytes)
        while True:
            if len(self._bytes) >= 10:
                num = int(self._bytes[0:10])
                if len(self._bytes) >= (10+num):
                    yield msgpack.unpackb(base64.a85decode(self._bytes[10:10+num]), encoding='utf-8')
                    self._bytes = self._bytes[10+num:]
                else:
                    break
            else:
                break
    def _build_agent(self):
        if self._agent is None:
            context = GLib.MainContext.new()
            self._nice_thread = NiceThread(context)
            self._nice_thread.start()
            agent = Nice.Agent.new_reliable(context, Nice.Compatibility.RFC5245)
            agent.controlling_mode = self._control
            stream = agent.add_stream(1)
            agent.set_stream_name(stream, 'text')
            agent.set_port_range(stream, 1, 5000, 5999)
            agent.connect('new-selected-pair-full',
                lambda agent, m, n, c1, c2: self._set_connected())
            agent.attach_recv(stream, 1, context,
                lambda a, m, n, sz, buf: self._data.put(buf)
            )
            self._agent = agent
            self._stream = stream
    def _request_candidates(self):
        if not self._started_find:
            self._started_find = True
            self._agent.connect('candidate-gathering-done',
                lambda instance, _: (
                    self._set_sdp(instance.generate_local_sdp())
                )
            )
            self._agent.gather_candidates(self._stream)

    def __init__(self, control):
        self._started_find = False
        self._offer = None
        self._answer = None
        self._connected = False
        self._control = control
        self._agent = None
        self._bytes = ''
        self._arr = []
        self._lock = Lock()
        self._data = Queue()

    def has_offer(self):
        return self._offer is not None
    def has_pair(self):
        return self.has_offer() and (self._answer is not None)
    def get_offer(self):
        return self._offer
    def has_conn(self):
        return self._connected
    def try_send(self, message):
        message = str(len(message)).ljust(10) + message
        print('GOAL SEND', message)
        if self._connected:
            print('ATTEMPTING SEND ', message)
            if self._agent.send(self._stream, 1, len(message), message) == len(message):
                print('DID SEND')
                return True
            else:
                raise Exception('Failed to send message.')
        else:
            return False

class OutgoingConnection(OneWayConnection):
    def _set_sdp(self, sdp):
       self._offer = sdp
    def request_offer(self):
        self._build_agent()
        super()._request_candidates()
    def set_answer(self, offer, answer):
        if offer == self._offer:
            self._answer = answer
            self._agent.parse_remote_sdp(answer)
            return True
        else:
            return False

class IncomingConnection(OneWayConnection):
    def _set_sdp(self, sdp):
        self._answer = sdp
        self._callback(sdp)
    def request_answer(self, callback):
        self._callback = callback
        super()._request_candidates()
    def set_offer(self, offer):
        self._offer = offer
        self._answer = None
        self._build_agent()
        self._agent.parse_remote_sdp(offer)


class TwoWayConnection:
    def log(self, *args):
        self._chump.log(f'@[{self._id}]', *args)

    def __init__(self, chump, id):
        self._chump = chump
        self._id = id
        self._outgoing = OutgoingConnection(True)
        self._incoming = []

    def has_conn(self):
        if self._outgoing.has_conn():
            return True
        for c in self._incoming:
            if c.has_conn():
                return True
        return False
    def make_offer(self):
        # If we have a connection, we don't need to send offers:
        if self.has_conn():
            pass
        # If we have an offer, though, we can return it:
        elif self._outgoing.has_offer():
            return self._outgoing.get_offer()
        # Otherwise, we want to request an offer:
        else:
            self._outgoing.request_offer()
    def got_offer(self, offer):
        if self.has_conn():
            pass
        else:
            incoming = IncomingConnection(False)
            incoming.set_offer(offer)
            incoming.request_answer(
                lambda answer: self._chump.send_answer(self._id, answer, offer)
            )
            self._incoming.append(incoming)
    def got_answer(self, pair):
        if self.has_conn():
            pass
        else:
            self._outgoing.set_answer(pair[0], pair[1])
    def try_send(self, message):
        if self._outgoing.try_send(message):
            print('SENT OUTGOING')
            return True
        for c in self._incoming:
            if c.try_send(message):
                print('SENT INCOMING')
                return True
        return False
    def read_messages(self):
        for c in self._incoming:
            yield from c.read_messages()
        yield from self._outgoing.read_messages()

class TcpDictionary(collections.defaultdict):
    def __init__(self, chump):
        super().__init__()
        self._chump = chump
    def __missing__(self, id):
        # print('MAKING: ', id)
        self[id] = TwoWayConnection(self._chump, id)
        return self[id]

class RecvThread(Thread):

    def __init__(self, stop_event, chump):
        super().__init__(daemon=True)
        self.daemon = True
        self._stop_event = stop_event
        # FIXME thread safety; broke TCP
        self._chump = chump
        self.doomed = Queue()
    def log(self, *args):
        self._chump.log('recv_thread', *args)
    def run(self):
        while not self._stop_event.is_set():
            with self._chump.lock:
                self.doom()
                self.sync()
            sleep(15) # TODO make configurable
        self.log('DONE!')
    def doom(self):
        to_doom = []
        while True:
            try:
                to_doom.append(self.doomed.get_nowait())
            except(Empty):
               break
        imap = self._chump.get_imap()
        self.log('DOOMING', to_doom)
        if len(to_doom) > 0:
            doomed = ','.join(to_doom)
            self.log('Dooming: ', doomed)
            self.log(imap.uid("STORE", doomed, '+FLAGS', '\\Deleted'))
            self.log(imap.uid("EXPUNGE", doomed))
            to_doom = []
    def sync(self):
        self.log('WILL SYNC')
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
            # self.log('MSG: {0} {1} {2}'.format(uid, message['Subject'], message.get_payload()))
            full_message = None
            try:
                # https://stackoverflow.com/questions/45124127/
                full_message = msgpack.unpackb(base64.a85decode(message.get_payload()), encoding='utf-8')
            except:
                # Just ignore seriously malformed messages
                pass
            if full_message is  not None and 'key' in full_message:
                if full_message['key'] == '__answer':
                    self.log('Got an answer of some sort...')
                    self._chump._tcp[full_message['sender']].got_answer(full_message['body'])
                    self.doomed.put(uid)
                else:
                    self._chump._queues[full_message['key']][uid] = full_message
                    if 'offer' in full_message:
                        self.log('GOT OFFER!')
                        offers.append(full_message)
        for offer in offers:
            self.log(f'Got offer')
            if 'timestamp' in offer:
                self.log(f'With stamp: {offer["timestamp"]}')
            self._chump._tcp[offer['sender']].got_offer(offer['offer'])
            offer['offer'] = 'X' # Hide from user
            # self.log('Message in old format!')
            # Do nothing - this isn't a CHUMP message


class ChumpServer:
    def got_tcp(self, full_message):
        self._tcp_messages[full_message['key']].append(full_message)

    def log(self, *args):
        if self._verbose:
            print(f'[{self.get_addr()}]', *args)

    def __init__(self, config_file):
        self._verbose = True # TODO change
        self._config = ConfigParser()
        self._config.read(config_file)
        self._smtp = None
        self._imap = None
        self._queues = defaultdict(dict)
        self._tcp_messages = defaultdict(list)
        self._tcp = TcpDictionary(self)
        self.lock = Lock()
        self._stop_event = Event()
        self._recv_thread = RecvThread(self._stop_event, self)
        self._recv_thread.start()

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
            imap.authenticate('PLAIN', lambda resp:
                "{0}\x00{0}\x00{1}".format(imap_config['user'], imap_config['password']).encode()
            )
            self._imap = imap
        return self._imap
    def send(self, key, recipients, message):
        if not isinstance(recipients, list):
            recipients = [recipients]
        recipients = [ x.get_addr()
            if isinstance(x, ChumpServer)
            else x
            for x in recipients ]
        smtp = self.get_smtp()
        full_message = {
            'key': key,
            'sender': self._config['email']['address'],
            'body': message,
            'timestamp': int(time()),
            'protocol': 'email'
        }
        new_recipients = []
        for r in recipients:
            inner_dict = full_message.copy()
            inner_dict['protocol'] = 'tcp'
            encoded = base64.a85encode(msgpack.packb(inner_dict, use_bin_type=True)).decode()
            if self._tcp[r].try_send(encoded):
                self.log('Trying to send succeeded...')
                # ..and don't append to new_recipients
                pass
            else:
                offer = self._tcp[r].make_offer()
                if offer is not None:
                    self.log(f'Providing offer... {full_message["timestamp"]}')
                    full_message['offer'] = offer
                new_recipients.append(r)
        recipients = new_recipients
        if len(recipients) > 0:
            msg = EmailMessage()
            msg['From'] = '<' + self._config['smtp']['from'] + '>'
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = base64.a85encode(str.encode(key)).decode()
            encoded = base64.a85encode(msgpack.packb(full_message, use_bin_type=True),wrapcol=80).decode()
            msg.set_content(encoded)
            smtp.send_message(msg)

    def send_answer(self, recipient, data, offer):
        self.log(f'Sending answer to {recipient}.')
        self.send('__answer', recipient, [offer, data])
        # self.read_from(recipient)

    def recv(self, key):
        with self.lock:
            # NOTE: we assume here that the 'sender' value in each message is correct
            # (i.e. we allow the other users to spoof their own addresses). Since this
            # whole thing is insecure anyway, it doesn't matter much.

            # 1. Get items from each TCP connection:
            for k, val in self._tcp.items():
                for msg in val.read_messages():
                    self.got_tcp(msg)
            mq = [x for x in self._tcp_messages[key]]
            self._tcp_messages[key] = []

            # 2. Get items from the receive thread's queue, and mark them for deletion:
            for uid, full_message in self._queues[key].items():
                self._recv_thread.doomed.put(uid)
                mq.append(full_message)
            self._queues[key] = {}

            # 3. Sort by timestamp so things are at least somewhat in order:
            mq.sort(key=
                lambda x: (x['timestamp'] if ('timestamp' in x) else 0)
            )
            return mq

    def store(self, key, message):
        keyEncoded = key;
        #keyEncoded = base64.a85encode(str.encode(key)).decode()
        messageEncoded = base64.a85encode(str.encode(message),wrapcol=80).decode()

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
        #keyEncoded = base64.a85encode(str.encode(key)).decode()

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