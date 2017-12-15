**Going Postal - CHUMP Daemon and Demo Application**

First, ensure pipenv is installed and install the required dependencies from the `chump` directory with `pipenv install`. Note that the application
requires Python 3.6 or later; Python 3.5 is *not* sufficient, and
the application will not work with Python 2.

This thing needs our forked version of libnice to run for fancy TCP things, but we've prebuilt that into this repo.  There is a build script for it though (`build-libnice.sh`) just in case.

Then, to run `chumpd`. For instance, if one wants to use the IMAP/SMTP configuration from `configs/gmail3.ini`, and to use a socket in `$HOME`, one might run the commmand:

```
pipenv run python3 chumpd.py configs/gmail3.ini ipc://$HOME/gmail3.socket
```

We've included config files for a few different email accounts already.  GMail seems to play the nicest so far.

You might run into some other strange dependency issues with GObject and python's gi module. The main trick is to ensure that GObject introspection
files are available for the relevant modules.

Once you get `chumpd` running, go to the `demo` directory and check out the demo app! You can also run the included unit tests and benchmark with `pipenv run python3 -m unittest -v -f tests.py`, though these aren't exactly well-organized.