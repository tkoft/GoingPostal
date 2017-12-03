Start chumpdt, the TCP version of chumpd since I can't get unix sockets to work in Electron.

`python3 chumpdt configs/gmail3.ini 2900`

Run app with:

`electron .`

or `./node_modules/.bin/electron .`
(needed on my machine - Jason)


Note to self: I had to change `zmq.target.mk` to remove dependency on `.a` file (for using `electron-rebuild`).

Issue: getting occasional errors.