**Going Postal - CHUMP Daemon and Demo Application**

First, ensure pipenv is installed and install the required dependencies from the `chump` directory with `pipenv install`.  

This thing needs libnice to run for fancy TCP things, but we've prebuilt that into this repo.  There is a build script for it though just in case.

Then, to run CHUMPd, for example with the gmail3.ini configuration and a unix socket at your home directory:

```
pipenv run python3 chumpd.py configs/gmail3.ini ipc://$HOME/gmail3.socket
```

We've included config files for a few different email accounts already.  Gmail seems to play the nicest so far.

You might run into some other strange dependency issues with gobject and python's gi module.  Godspeed.

Once you get CHUMPd running, go to the `demo` directory and check out the demo app!