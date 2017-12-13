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
from threading import Thread
import msgpack
import zerorpc
import os
from unittest import TestCase
from time import sleep, time
import re
import base64
import email
import collections
from operator import itemgetter, attrgetter


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
# FIXME: recv *sometimes* works
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

# TODO: deduplicate TCPs so we don't hava emultiple overlapping negotations

# Tests.
# Example: pipenv run python3 -m unittest chumpd.py
# TODO: write tests for CLI, and various special cases; speed this up
class BasicTest(TestCase):
    def test_tcp(self):
        with ChumpServer('configs/gmail3.ini') as gmail3, \
            ChumpServer('configs/gmail2.ini') as gmail2:
            print('Starting...')
            gmail2.send('app', gmail3, 'M1')
            sleep(30)
            # sleep(30) # Try to get a candidate... should show 'Adding offer'
            print('SHOULD SEND OFFER:')
            gmail2.send('app', gmail3, 'M2') # Send an offer
            sleep(10)
            print('SHOULD RECEIVE OFFER and SEND ANSWER:')
            print(gmail3.recv('app')) # get the offer, send an answer
            sleep(50)
            print('SHOULD RECEIVE ANSWER:')
            print(gmail2.recv('app')) # get the answer!
            sleep(30)
            print('SHOULD HAVE CONNECTION:')
            gmail2.send('app', gmail3, 'M3') # Connection established
            sleep(5)
            print(gmail3.recv('app'))  # recv over tcp

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

def get_sdp(agent, stream, callback):
    agent.connect('candidate-gathering-done',
        lambda instance, _:
            [print('HERE: '), callback(instance.generate_local_sdp())],
    )
    agent.gather_candidates(stream)



id = 0

# The main server object
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

class TcpConnectionManager:
    def __init__(self,chump, id):
        self._chump = chump
        self._id = id
        self._offer = None
        self._connection = False
        self._context = GLib.MainContext.new()
        self._nice_thread = NiceThread(self._context)
        self._nice_thread.start()
        self._no_provide = False
        self._messages = []

    def get_messages(self):
        m = self._messages
        self._messages = []
        return m

    def state_changed(self, *args):
        # FIXME: gives state 'FAILED'
        self.log('New state: ', *args)

    def has_chan(self, *args):
        self.log('Has chan: ', *args)
    def log(self, *args):
        self._chump.log(f'@[{self._id}]', *args)
    def got_answer(self, answer):
        if answer[0] == self._offer:
            self.log('Answer matches!')
            self._agent.parse_remote_sdp(answer[1])
            # self.read_from(sender)
        else:
            self.log('INVALID!')
    def make_agent(self, control, callback):
        agent = Nice.Agent.new_reliable(self._context, Nice.Compatibility.RFC5245)
        agent.controlling_mode = control

        # FIXME: shows too many offers
        # agent.connect('component-state-changed', self.state_changed)

            # or should it be when component-state changes?
        stream = agent.add_stream(1)
        agent.set_stream_name(stream, 'text')
        agent.set_port_range(stream, 1, 5000, 5999)

        agent.connect('new-selected-pair-full',
            lambda agent, m, n, c1, c2:
                callback()
            )
        agent.attach_recv(
            stream,
            1,
            self._nice_thread.context,
            lambda a, m, n, sz, buf: self._messages.append(buf)
        )
        self._agent = agent
        self._stream = stream
    def _set_offer(self,x):
        self.log('Made an offer!')
        self._offer = x
    def _got_connection(self):
        # self.log('Connected', x)
        self._connection = True
    def setup(self, offer):
        if offer is None and self._offer is None:
            self._offer = True
            self.make_agent(True, self._got_connection)
            get_sdp(self._agent, self._stream, self._set_offer)
        elif (offer is not None) and (self._offer is None) and (not self._connection):
            self._no_provide = True
            # TODO make sure we're not in the progres of making an answer; generally consider state machine here
            self._offer = offer
            self.make_agent(False, self._got_connection)
            if self._agent.parse_remote_sdp(offer) < 0:
                self.log('Failed SDP parsing!')
            else:
                self.log('Getting SDP...')
                get_sdp(self._agent, self._stream,
                    lambda x: self._chump.send_answer(self._id, x, offer)
                )
    def make_offer(self):
        if self._offer is None:
            self.setup(None)
            return None
        elif self._offer is True or self._no_provide:
            return None
        else:
            # TODO: don't send offer if we're the answerer
            return self._offer
    def try_send(self, message):
        if self._connection:
            # FIXME: don't ALSO send over email in this case
            mstr = message# .decode('utf-8') # will unicode really work here?
            self.log(
                'Send result: ',
                self._agent.send(self._stream, 1, len(mstr), mstr)
            )
            return True
        else:
            return False


class TcpDictionary(collections.defaultdict):
    def __init__(self, chump):
        super().__init__()
        self._chump = chump
    def __missing__(self, id):
        print('MAKING: ', id)
        self[id] = TcpConnectionManager(self._chump, id)
        return self[id]

class ChumpServer:

    def log(self, *args):
        print(f'[{self.get_addr()}]', *args)

    def __init__(self, config_file):
        self._config = ConfigParser()
        self._config.read(config_file)
        self._smtp = None
        self._imap = None
        self._queues = defaultdict(dict)
        self._doomed = []
        self._tcp = TcpDictionary(self)
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

    def send(self, key, recipients, message): #
    # do we want to allow spoofing?
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
            encoded = base64.a85encode(msgpack.packb(inner_dict, use_bin_type=True),wrapcol=80).decode()
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

    # TODO: poll, send/receive on interval
    # TODO: make methods private
    # TODO: may need to use nice_agent_attach_recv () for 'stuun' to work
    #    -> don't use nice_agent_recv_messages
    # TODO: think through TCP state machine; add duplex support


    def sync(self):
        # Use 'UID' command whenever possible.        id += 1
        # RECENT internally does a NOP just to get a reaction
        # We can use \\Recent to ensure that no one else has seen!
        imap = self.get_imap()
        typ, count = imap.select()
        count = count[0].decode()
        if count == '0':
            return []
        # could use SEARCH to narrow this down (or THREAD)
        typ, data = imap.fetch('1:*', '(UID RFC822)')
        # self.log(data)
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
                subj = base64.a85decode(message['Subject']).decode()
                # https://stackoverflow.com/questions/45124127/
                full_message = msgpack.unpackb(base64.a85decode(message.get_payload()), encoding='utf-8')
            except:
                # Just ignore seriously malformed messages
                pass
            # self.log('Msg: ', uid, full_message)
            if full_message is  not None and 'key' in full_message:
                if full_message['key'] == '__answer':
                    self.log('Got an answer of some sort...')
                    self._tcp[full_message['sender']].got_answer(full_message['body'])
                    self._doomed.append(uid)
                else:
                    self._queues[full_message['key']][uid] = full_message
                    if 'offer' in full_message:
                        offers.append(full_message)
        # always look at more recent offers first, since they
        # have a greater likelihood of success.
        offers.sort(key=
            lambda x: (x['timestamp'] if ('timestamp' in x) else 0)
        )
        offers.reverse()
        for offer in offers:
            self.log(f'Got offer')
            if 'timestamp' in offer:
                self.log(f'With stamp: {offer["timestamp"]}')
            self._tcp[offer['sender']].setup(offer['offer'])
            # self.log('Message in old format!')
            # Do nothing - this isn't a CHUMP message
    def doom(self):
        imap = self.get_imap()
        if len(self._doomed) > 0:
            doomed = ','.join(self._doomed)
            self.log('Dooming: ', doomed)
            self.log(imap.uid("STORE", doomed, '+FLAGS', '\\Deleted'))
            self.log(imap.uid("EXPUNGE", doomed))
            self._doomed = []
    def recv(self, key):
        self.sync()
        mq = []
        for k, val in self._tcp.items():
            # TODO filter by key, unbase85 and unmsgpack
            # we do need to base85 b/c of unicode-y issues (workaround somehow?)
            mq.extend([
                 msgpack.unpackb(base64.a85decode(message), encoding='utf-8')
                 for message
                 in val.get_messages()
            ])
        # TODO: use a 'real' debugger?
        # self.log('Q', self._queues)
        for uid, full_message in self._queues[key].items():
            # self.log('Message', full_message)
            self._doomed.append(uid)
            mq.append(dict(sender=full_message['sender'],body=full_message['body']))
        self.doom()
        self._queues[key] = {}
        return mq

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