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
from threading import Thread, Lock, Timer, Event, RLock
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
from uuid import uuid4
from chumpd import ChumpServer


# Tests.
# Example: pipenv run python3 -m unittest -vf tests.py

class TcpTest(TestCase):
    def test_tcp(self):
        with ChumpServer('configs/gmail3.ini') as right, \
            ChumpServer('configs/gmail2.ini') as left:
            # Clean out queues and send initial message
            left.recv('app')
            right.recv('app')
            left.send('app', right, 'M1')
            while not left.tcpdict[right.get_addr()]._outgoing.has_offer():
                sleep(1)
            left.send('app', right, 'M2') # Send an offer

            sleep(30)

            self.assertEqual(left.recv('app'), [])
            self.assertEqual(
                [{**x, 'timestamp': 0} for x in right.recv('app')],
                [
                    {'key': 'app', 'sender': left.get_addr(), 'body': 'M1', 'timestamp':0, 'protocol': 'email'}
                    ,{'key': 'app', 'sender': left.get_addr(), 'body': 'M2', 'timestamp':0, 'protocol': 'email'}
                ]
            )
            print('Waiting...')
            while not right.tcpdict[left.get_addr()].has_conn():
                sleep(1)
            while not left.tcpdict[right.get_addr()].has_conn():
                sleep(1)

            left.send('app', right, 'M3A')
            right.send('app', left, 'M3B')
            right.send('app', left, 'M3C')
            left.send('app', right, 'M3D')
            left.send('app', right, 'M3E')

            sleep(5)

            self.assertEqual(
                [{**x, 'timestamp': 0} for x in left.recv('app')],
                [
                    {'key': 'app', 'sender': right.get_addr(), 'body': 'M3B', 'timestamp':0, 'protocol': 'tcp'}
                    ,{'key': 'app', 'sender': right.get_addr(), 'body': 'M3C', 'timestamp':0, 'protocol': 'tcp'}
                ]
            );
            self.assertEqual(
                [{**x, 'timestamp': 0} for x in right.recv('app')],
                [
                    {'key': 'app', 'sender': left.get_addr(), 'body': 'M3A', 'timestamp':0, 'protocol': 'tcp'}
                    ,{'key': 'app', 'sender': left.get_addr(), 'body': 'M3D', 'timestamp':0, 'protocol': 'tcp'}
                    ,{'key': 'app', 'sender': left.get_addr(), 'body': 'M3E', 'timestamp':0, 'protocol': 'tcp'}
                ]
            );

class BasicTest(TestCase):
    def _remove_timestamps_offers(self, list):
        return [{**x, 'timestamp': 0, 'offer': '?'} for x in list]

    def test_imap(self):
        with ChumpServer('configs/gmail3.ini') as gmail3, \
            ChumpServer('configs/gmail2.ini') as gmail2, \
            ChumpServer('configs/yahoo1.ini') as yahoo1:
            # Test 'recv'
            yahoo1.recv('app')
            gmail3.recv('app')
            self.assertEqual(yahoo1.recv('app'), [], 'Yahoo is empty')
            self.assertEqual(gmail3.recv('app'), [], 'Gmail is empty')
            gmail2.send('app', [gmail3.get_addr(), yahoo1], 'ABC')
            gmail2.send('app', gmail3.get_addr(), 'DEF')
            gmail2.send('app', yahoo1.get_addr(), 'DEF')
            sleep(30)
            rec1 = self._remove_timestamps_offers(gmail3.recv('app'))
            rec2 = self._remove_timestamps_offers(yahoo1.recv('app'))
            expected = [
                {'key': 'app', 'sender': gmail2.get_addr(), 'body': 'ABC', 'timestamp':0, 'protocol': 'email', 'offer': '?'},
                {'key': 'app', 'sender': gmail2.get_addr(), 'body': 'DEF', 'timestamp':0, 'protocol': 'email', 'offer': '?'}
            ]
            self.assertCountEqual(rec1, expected, 'Gmail3 works')
            self.assertCountEqual(rec2, expected, 'Yahoo1 works')

    def test_store(self):
        with ChumpServer('configs/yahoo1.ini') as yahoo1:
            data = str(uuid4())
            yahoo1.store('test-key', data)
            self.assertEqual(yahoo1.retrieve('test-key'), data)

id = str(uuid4())

class BenchThread(Thread):
    def run(self):
        global id
        with ChumpServer('configs/gmail1.ini') as gmail2:
                for i in range(0,20):
                    gmail2.send(id, 'gonepostal003@gmail.com', 'L' + str(i))
                    sleep(10)

class BenchTwo(Thread):
    def run(self):
        global id
        with  ChumpServer('configs/gmail3.ini') as gmail3:
            messages = []
            while len(messages) < 20:
                for msg in gmail3.recv(id):
                    print('TIME=', int(time()) - msg['timestamp'], msg['protocol'])
                    messages.append(msg)
                sleep(1)


class BenchTest(TestCase):
    def test_benchmark(self):
        t = BenchTwo()
        t.start()
        BenchThread().start()
        t.join()