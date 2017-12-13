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
from time import sleep
import re
import base64
import email
import collections



# WORKS!!!! RECEIVE SUCCEEDS!
# TO INTEGRATE WITH API, CLEANUP ETC
#  - sems to work *although* state goes to 5 sometimes???

# FIXME: current issue -- sending works but recv doesn't
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
            while gmail3.get_addr() not in gmail2._tcp_off \
                or gmail2._tcp_off[gmail3.get_addr()] == False:
                sleep(1)
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
            sleep(30)
            print(gmail3.recv('app'))  # recv over tcp
            sleep(30)

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
        self.daemon = True
    def run(self):
        self.context = GLib.MainContext.new()
        GLib.MainLoop.new(self.context, False).run()

def get_sdp(agent, stream, callback):
    agent.connect('candidate-gathering-done',
        lambda instance, _:
            callback(instance.generate_local_sdp()),
    )
    agent.gather_candidates(stream)



class ReaderThread(Thread):
    def __init__(self, agentinfo):
        super().__init__(daemon=True)
        self.daemon = True
        self._ai = agentinfo
        # help(agentinfo.agent)
    def run(self):
        # See https://phabricator.freedesktop.org/T7895
        while True:
            print('Reading...')
            try:
                # *segfaults* sometimes.
                # 'read' "works" but sometimes doesn't.
                res = self._ai.agent.recv(
                    self._ai.stream,
                    1,
                    None
                )
                print('Did read: ', res)
            except:
                print('Read err')
                sleep(10)
            # self._ai.agent.recv_messages(
            #     self._ai.stream,
            #     1,
            #     None
            # )



id = 0

# The main server object
# TODO: test TCP with multicast, multiple simultaneous connections
# TODO: error handling; see powerpoint and things we gave to Jeannie
# FIXME: I'm going to have serious issues with how 'recv' works
#  -- attach_recv is needed for stun and it isn't introspectable...
# TODO: send and receive successfully over TCP
#     ^ and *reliably* do so -- ti fails sometimes now with 'invalid answer'
#     ^ may want to increase stun-pacing-timer

class ChumpServer:

    def log(self, *args):
        print(f'[{self.get_addr()}]', *args)

    def make_agent(self, control, callback):
        # Must be 'reliable' for streaming I/O to work;
        # non-streaming IO is broken in Python since attach_recv
        # isn't introspectable.
        agent = Nice.Agent.new_reliable(self._nice_thread.context, Nice.Compatibility.RFC5245)

        agent.controlling_mode = control


        agent.connect('component-state-changed', self.state_changed)

            # or should it be when component-state changes?
        stream = agent.add_stream(1)
        agent.set_stream_name(stream, 'text')
        agent.set_port_range(stream, 1, 5000, 5999)
        ainfo = AgentInfo(agent=agent, stream=stream)
        agent.connect('new-selected-pair-full',
            lambda agent, m, n, c1, c2:
                callback(ainfo)
            )

        # self.log(agent.recv(buf, 1024))
        # ReaderThread(AgentInfo(agent=agent, stream=stream)).start()

#          * @agent: The #NiceAgent Object
#  * @stream_id: The ID of stream
#  * @component_id: The ID of the component
#  * @ctx: The Glib Mainloop Context to use for listening on the component
#  * @func: (scope async): The callback function to be called when data is received on
#  * the stream's component (will not be called for STUN messages that
#  * should be handled by #NiceAgent itself)
#  * @data: user data associated with the callback
#  *
        agent.attach_recv(
            stream,
            1,
            self._nice_thread.context,
            lambda *args: self.log('Got', args)
        )
        return (agent, stream)


    def __init__(self, config_file):
        global id
        self._config = ConfigParser()
        self._config.read(config_file)
        self._smtp = None
        self._imap = None
        self._queues = defaultdict(dict)
        self._doomed = []
        self._tcp_off = {}
        self._tcp_conn = {}
        self._tcp_ans = {}
        self._tcp_agents = {}
        self._nice_thread = NiceThread()
        self._nice_thread.start()
        self._id = id
        id += 1
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
        self._tcp_off[recipient] = False # marker
        agent, stream = self.make_agent(True,
            lambda ainfo: self._tcp_conn.__setitem__(recipient, ainfo)
        )
        get_sdp(agent, stream,
            lambda x: self._tcp_off.__setitem__(recipient, x))
        self._tcp_agents[recipient] = AgentInfo(agent=agent, stream=stream)


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
            'body': message
        }
        for r in recipients:
            if r in self._tcp_conn:
                self.log('HAVE CONNECTION!')
                # FIXME: don't end over email in this case
                ainf = self._tcp_conn[r]
                self.log(
                    'Send result: ',
                    ainf.agent.send(ainf.stream, 1, 12, 'abcabcabcabc')
                )
            elif r in self._tcp_off:
                if self._tcp_off[r] is not False:
                    self.log('Adding offer')
                    full_message['offer'] = self._tcp_off[r]
            else:
                # prepare for TCP, but we won't hav ean offer available yet
                # should we *block* here in case an offer becomes available?
                self.setup_tcp(r)
        msg = EmailMessage()
        msg['From'] = '<' + self._config['smtp']['from'] + '>'
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = base64.a85encode(str.encode(key)).decode()
        msg.set_content(base64.a85encode(msgpack.packb(full_message),wrapcol=80).decode())
        smtp.send_message(msg)

    def state_changed(self, *args):
        # FIXME: gives state 'FAILED'
        self.log('New state: ', *args)

    def has_chan(self, *args):
        self.log('Has chan: ', *args)


    # def read_from(self, sender):
    #     self.log('Will read!')
    #     stuff = [0]*1024

    #     agentinfo = self._tcp_agents[sender]
    #     agentinfo.agent.recv_messages(
    #         agentinfo.stream,
    #         1,
    #         13,
    #         None
    #     )
        # do this on a thread somehow?
        # agentinfo.agent.get_io_stream(agentinfo.stream, 1) \
        #     .get_input_stream() \
        #     .read_bytes_async(1024, 0, None,
        #         lambda x: self.log('Did read ', x))
        # self.log('Did read!')

    def send_answer(self, recipient, data, offer):
        self.log(f'Sending answer to {recipient}.')
        self.send('__answer', recipient, [offer, data])
        # self.read_from(recipient)

    # TODO: poll, send/receive on interval
    # TODO: make methods private
    # TODO: may need to use nice_agent_attach_recv () for 'stuun' to work
    #    -> don't use nice_agent_recv_messages
    # TODO: think through TCP state machine; add duplex support

    def handle_offer(self, sender, offer):
        self.log('Handling offer; will attempt to generate answer.')
        agent, stream = self.make_agent(False,
            lambda *args: self.log('Has channel!')
        )
        self._tcp_agents[sender] = AgentInfo(agent=agent, stream=stream)
        if agent.parse_remote_sdp(offer) < 0:
            self.log('Failed SDP parsing!')
        else:
            get_sdp(agent, stream,
                lambda x: self.send_answer(sender, x, offer)
            )

    def got_answer(self,sender, answer):
        if answer[0] == self._tcp_off[sender]:
            self.log('Answer matches!')
            agentinfo = self._tcp_agents[sender]
            agentinfo.agent.parse_remote_sdp(answer[1])
            # self.read_from(sender)
        else:
            self.log('INVALID!')

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
        # self.log(data)
        messages = [ x
            for x in data
            if isinstance(x, tuple) ]
        for (mkey, mvalue) in messages:
            message = email.message_from_string(mvalue.decode())
            uid = re.search(rb'UID\s*(\d+)', mkey).group(1).decode()
            # self.log('MSG: {0} {1} {2}'.format(uid, message['Subject'], message.get_payload()))
            try:
                subj = base64.a85decode(message['Subject']).decode()
                # https://stackoverflow.com/questions/45124127/
                full_message = msgpack.unpackb(base64.a85decode(message.get_payload()), encoding='utf-8')
                # self.log(full_message)
                # TODO: verify that the answer has [0] as current outstanding offer
                # and [1] will contain

                if full_message['key'] == '__answer':
                    self.got_answer(full_message['sender'], full_message['body'])
                    self._doomed.append(uid)
                else:
                    self._queues[subj][uid] = full_message
                    if full_message['offer'] and not full_message['sender'] in self._tcp_off  and not full_message['sender'] in self._tcp_conn:
                        self.handle_offer(full_message['sender'], full_message['offer'])
            except:
                # Just ignore malformed messages
                pass
                # self._doomed.append(uid) <- in future
                # self.log('Message in old format!')
                # Do nothing - this isn't a CHUMP message
    def doom(self):
        imap = self.get_imap()
        if len(self._doomed) > 0:
            doomed = ','.join(self._doomed)
            self.log('Dooming: ', doomed)
            self.log(imap.uid("STORE", doomed, '+FLAGS', '\\Deleted'))
            self.log(imap.expunge())
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