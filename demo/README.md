Start chumpdt, the TCP version of chumpd since I can't get unix sockets to work in Electron.

`python3 chumpd configs/gmail3.ini ipc://$HOME/test.sock`

Run app with:

`SOCKET=ipc://$HOME/test.sock electron .`

or `./node_modules/.bin/electron .`
(needed on my machine - Jason)


Note to self: I had to change `zmq.target.mk` to remove dependency on `.a` file (for using `electron-rebuild`).

Issue: Getting occasional "routing" errors from ZeroMQ. Try to get this working with unix sockets?