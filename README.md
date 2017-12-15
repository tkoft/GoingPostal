Going Postal - CHUMP Daemon and Demo Application

To run the CHUMP Daemon, for example with the gmail3.ini configuration and a unix socket at your home directory:

pipenv run python3 chumpd.py configs/gmail3.ini ipc://$HOME/gmail3.socket

