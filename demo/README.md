Start chumpdt, the TCP version of chumpd since I can't get unix sockets to work in Electron.

`pipenv run python3 chumpd configs/gmail3.ini ipc://$HOME/test.sock`

Run app with:

`SOCKET=ipc://$HOME/test.socket ./node_modules/.bin/electron .`

If you get node version mismatch errors, update node, delete dependencies from package.json, delete the node_modules directory, and `npm install electron zeromq zerorpc`

Note to self: I had to change `zmq.target.mk` to remove dependency on `.a` file (for using `electron-rebuild`).

Issue: Getting occasional "routing" errors from ZeroMQ. Try to get this working with unix sockets?