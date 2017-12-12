
# note: you need pygobject working,
# and Sony Ericsson's openwebrtc installed; this has to be compiled with introspection.
# i'm using the latest version of this from git.
# see: https://github.com/EricssonResearch/openwebrtc/issues/394#issuecomment-218276247

# TODO: actually test this on separate devices, with a nat;
# will need to serialize ICE candidates
# - will I need to use `freeice` or similar?

import gi
gi.require_version('Owr', '0.3')
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import Owr

left_session = None
right_session = None
left_ch = None
right_ch = None
left_candidates = []
right_candidates = []
count = 2


def got_data(*args):
    print(*args)

def got_request(instance, *args):
    global left_session, right_session, left_ch, right_ch
    print('here2')
    print(instance)
    print(args)
    left_ch = Owr.DataChannel.new(*args)
    left_session.add_data_channel(left_ch)
    right_ch.connect('on-binary-data', got_data)
    left_ch.send_binary(b'test')
    print('Hello!')
    


def all_done():
    global left_session, right_session, left_ch, right_ch
    print('Hello world!')
    left_session.connect('on-data-channel-requested', got_request)
    # 41 must be *odd*
    # 1 gets intentionally *reused* - this is *right* I believe
    right_ch = Owr.DataChannel.new(False, 5000, -1, "OTP", False, 1, 'requested')
    right_session.add_data_channel(right_ch)
    print('here')

def count_done(inst, x):
    global count
    count -= 1
    if count == 0:
        all_done()

def left_done(instance):
    global left_candidates, right_session, count
    for c in left_candidates:
        right_session.add_remote_candidate(c)

def right_done(instance):
    global right_candidates, left_session, count
    for c in right_candidates:
        left_session.add_remote_candidate(c)


def left_candidate(instance, candidate):
    global left_session, left_candidates
    left_candidates.append(candidate)

def right_candidate(instance, candidate):
    global left_session, right_candidates
    right_candidates.append(candidate)

def setup():
    global left_session, right_session
    left = Owr.TransportAgent.new(False)
    right = Owr.TransportAgent.new(True)
    left.set_local_port_range(5000, 5999)
    right.set_local_port_range(5000,5999)
    left.add_local_address('127.0.0.1')
    right.add_local_address('127.0.0.1')
    left_session = Owr.DataSession.new(True)
    right_session = Owr.DataSession.new(False)
    left_session.set_property('sctp-local-port', 5000)
    right_session.set_property('sctp-local-port', 5000)
    left_session.set_property('sctp-remote-port', 5000)
    right_session.set_property('sctp-remote-port', 5000)
    left_session.connect('on-new-candidate', left_candidate)
    right_session.connect('on-new-candidate', right_candidate)
    left_session.connect("on-candidate-gathering-done", left_done)
    right_session.connect("on-candidate-gathering-done", right_done)
    
    # g_object_set(left_session, "sctp-local-port", 5000, "sctp-remote-port", 5000, NULL);
    # g_object_set(right_session, "sctp-local-port", 5000, "sctp-remote-port", 5000, NULL);
    #     g_signal_connect(left_session, "on-new-candidate", G_CALLBACK(got_candidate), right_session);
    # g_signal_connect(right_session, "on-new-candidate", G_CALLBACK(got_candidate), left_session);
    left.add_session(left_session)
    right.add_session(right_session)
    left_session.connect("notify::dtls-peer-certificate", count_done)
    right_session.connect("notify::dtls-peer-certificate", count_done)
    print(dir(left))


# borrowed from ericsson code a bit here

def main():
    mc = GLib.MainContext.get_thread_default()
    if not mc:
        mc = GLib.MainContext.default()
    Owr.init(mc)
    setup()
    Owr.run()
    print("exiting")

if __name__ == '__main__':
    main()
