**DEMO APP - CRAPCHAT for Gone Postal Final Project**
Gary Chen, Jason Hansel

This is a barebones demo app for CHUMP.  It uses its messaging capabilities to send image messages that totally aren't like Snapchat, and also persists some data on the email server like a friends list and unread messages, also through the CHUMP protocol.

Ensure you have chumpd started before you start the demo app.
Also ensure you have the lastest version of nodejs (like, version 9 or so). 
Install node dependencies with:

```
npm install
```

Then, with the same socket you specified to chumpd, run app with:

```
SOCKET=ipc://$HOME/test.socket ./node_modules/.bin/electron .
```

If you get node version mismatch errors, update node, delete all dependencies from package.json, delete the node_modules directory, and manually install:

```
npm install electron zeromq zerorpc
```

Electron might complain about not having libgconf-2-4 installed, so:
```
sudo apt install libgconf-2-4
```

