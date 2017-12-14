
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

class NiceThread(Thread):
    def __init__(self, context):
        super().__init__(daemon=True)
        self.daemon = True
        self.context = context
    def run(self):
        GLib.MainLoop.new(self.context, False).run()



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
        # print('GOAL SEND', message)
        if self._connected:
            # print('ATTEMPTING SEND ', message)
            if self._agent.send(self._stream, 1, len(message), message) == len(message):
                # print('DID SEND')
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
    def get_answer(self):
        return self._answer


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
        self.log('Got offer!')
        if self.has_conn():
            pass
        elif offer in self._incoming:
            conn = self._incoming[offer]
            if conn.has_pair():
                self._chump._send_answer(self._id,
                    conn.get_answer(),
                    conn.get_offer(),
                )
            self.log('Redundant offer!')
            pass
        else:
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
            # print('SENT OUTGOING')
            return True
        for _, c in self._incoming.items():
            if c.try_send(message):
                # print('SENT INCOMING')
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
        # print('MAKING: ', id)
        self[id] = TwoWayConnection(self._chump, id)
        return self[id]
