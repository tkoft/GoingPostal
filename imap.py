from imaplib import IMAP4_SSL
from datetime import datetime
from smtplib import SMTP_SSL
from email.message import EmailMessage
import zerorpc

# using pipenv; use `pipenv run python imap.py` to test, I think
# `zerorpc -j ipc:///home/work/test.run send` eg.

class ChumpServer:
    def send(self):
        with SMTP_SSL("smtp.gmail.com", 465) as smtp:
            # I'm not worried about people stealing this password
            # gonepostal002 has same PW
            smtp.login("gonepostal001@gmail.com", "thisisnotsecret")
            print(smtp.verify("gonepostal001@gmail.com"))
            msg = EmailMessage()
            msg['From'] = '<gonepostal001@gmail.com>'
            msg['To'] = 'gonepostal002@gmail.com'
            msg.set_content('Hello world!')
            print(smtp.send_message(msg))
    def recv(self):
        with IMAP4_SSL("imap.gmail.com", 993) as imap:
            # nb: can use OAuth tokens.
            print(imap.authenticate('PLAIN', lambda resp:
                "{0}\x00{0}\x00{1}".format("gonepostal002@gmail.com","thisisnotsecret").encode()
            ))
            print(imap.select())
            typ, data = imap.search(None, 'ALL')
            return data
            # should pass flags as r'(\Deleted)` eg.
        # may want to use 'Referecnes' header
        #  https://stackoverflow.com/questions/7310003/search-imap-using-parsed-date-from-another-email
        
        
s = zerorpc.Server(ChumpServer())
s.bind("ipc:///home/work/test.run")
s.run()


# run: python3 imap.py
# today = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")
# get a proper ide for this
#     res = M.append('INBOX', r'(\Flagged)', None, """
# From: <gonepostal001@gmail.com>
# Date: {date}
# """.format(date=today).encode())
    # print(res)