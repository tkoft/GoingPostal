
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

# A simple thread to call GMainLoop, which libnice uses.
# We use a separate NiceThread per connection for testing purposes.
class NiceThread(Thread):
    def __init__(self, context):
        super().__init__(daemon=True)
        self.daemon = True
        self.context = context
    def run(self):
        GLib.MainLoop.new(self.context, False).run()


# TCP connections are of two types:
# - Outgoing connections are ones which we offer to the recipient;
#   the recipient must provide an answer for the connection to complete.
# - Incoming connections are ones which the recipient offers to us;
#   we must provide an answer for the connection to complete.
# The below code is shared between connections of both types.
class OneWayConnection:
    def __init__(self, control):
        self._started_find = False
        self._offer = None
        self._answer = None
        self._connected = False
        self._control = control
        self._agent = None
        self._arr = []
        # Unfortunately, the Python API to libnice requires us to use
        # strings to represent binary data. For now, we work around this
        # via base85 encoding; ideally, we should change the libnice
        # annotations to fix this.
        self._bytes = ''
        self._data = Queue()
    def _set_connected(self):
        self._connected = True
    # Take all the data received so far (on NiceThread) and yield
    # the resulting messages.
    def read_messages(self):
        while True:
            try:
                self._bytes += self._data.get_nowait()
            except(Empty):
               break
        while '\n' in self._bytes:
            len = self._bytes.index('\n')
            msg = self._bytes[0:len]
            yield msgpack.unpackb(base64.a85decode(msg), encoding='utf-8')
            self._bytes = self._bytes[len+1:]
    # Create a NiceAgent, used to handle the offer/answer exchange.
    def _state_changed(self, inst, m, n, state):
        if state == 4:
            self._connected = True
    def _build_agent(self):
        if self._agent is None:
            context = GLib.MainContext.new()
            self._nice_thread = NiceThread(context)
            self._nice_thread.start()
            agent = Nice.Agent.new_reliable(context, Nice.Compatibility.RFC5245)
            agent.controlling_mode = self._control
            stream = agent.add_stream(1)
            agent.set_stream_name(stream, 'text')
            agent.stun_pacing_timer = 300
            agent.set_port_range(stream, 1, 5000, 5999)
            # agent.connect('new-selected-pair-full',
            #     lambda agent, m, n, c1, c2: self._set_connected())
            agent.connect('component-state-changed', self._state_changed)
            #     lambda inst, m, n, state: self._set_connected() if state == 4 else False)
            agent.attach_recv(stream, 1, context,
                lambda a, m, n, sz, buf: self._data.put(buf)
            )
            self._agent = agent
            self._stream = stream
    # Used to generate either an offer or an answer.
    def _request_candidates(self):
        if not self._started_find:
            self._started_find = True
            self._agent.connect('candidate-gathering-done',
                lambda instance, _: (
                    self._set_sdp(instance.generate_local_sdp())
                )
            )
            self._agent.gather_candidates(self._stream)
    # Various helpers:
    def has_offer(self):
        return self._offer is not None
    def has_pair(self):
        return self.has_offer() and (self._answer is not None)
    def get_offer(self):
        return self._offer
    def has_conn(self):
        return self._connected
    # Try to send a message; returns false if we're not yet connected.
    def try_send(self, message):
        message = message + '\n'
        if self._connected:
            if self._agent.send(self._stream, 1, len(message), message) == len(message):
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
    def _state_changed(self, inst, m, n, state):
        super()._state_changed(inst, m, n, state)
        if state == 5:
            # TODO: Investigate the most common causes of this.
            # Likely involves timeouts.
            raise Exception('Connection failed!')
    def set_answer(self, offer, answer):
        if offer == self._offer:
            print('Got answer:')
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
    def get_answer(self):
        return self._answer

# This represents all of the connections between the current host
# and another CHUMP server. We need this because we might try to
# negotiate an outgoing and an incoming connection at the same time;
# in fact, we could accidentally end up with multiple incoming connections,
# if we receive multiple offers.
class TwoWayConnection:
    def log(self, *args):
        self._chump.log(f'@[{self._id}]', *args)

    def __init__(self, chump, id):
        self._chump = chump
        self._id = id
        self._outgoing = OutgoingConnection(True)
        self._incoming = {}

    def has_conn(self):
        if self._outgoing.has_conn():
            return True
        for _, c in self._incoming.items():
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
            self.log('Pointless offer')
            pass
        elif offer in self._incoming:
            self.log('Redundant offer')
            # conn = self._incoming[offer]
            # if conn.has_pair():
            #     # Send another answer, in case that helps
            #     self._chump._send_answer(self._id,
            #         conn.get_answer(),
            #         conn.get_offer(),
            #     )
            pass
        else:
            self.log('Novel offer')
            incoming = IncomingConnection(False)
            incoming.set_offer(offer)
            incoming.request_answer(
                lambda answer: self._chump._send_answer(self._id, answer, offer)
            )
            self._incoming[offer] = incoming
    def got_answer(self, pair):
        if self.has_conn():
            self.log('Redundant answer!')
            pass
        else:
            self.log('Got answer')
            self._outgoing.set_answer(pair[0], pair[1])
    def try_send(self, message):
        if self._outgoing.try_send(message):
            return True
        for _, c in self._incoming.items():
            if c.try_send(message):
                return True
        return False
    def read_messages(self):
        for _, c in self._incoming.items():
            yield from c.read_messages()
        yield from self._outgoing.read_messages()

class TcpDictionary(collections.defaultdict):
    def __init__(self, chump):
        super().__init__()
        self._chump = chump
    def __missing__(self, id):
        self[id] = TwoWayConnection(self._chump, id)
        return self[id]
