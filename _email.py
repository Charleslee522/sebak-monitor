import smtplib
import logging
import traceback
import email.utils
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


log = logging.getLogger(__name__)


class SMTP(smtplib.SMTP):
    message_id = None

    def _print_debug(self, *a, **kw):
        if len(a) < 2:
            return

        if a[0] not in ('data:',):
            return

        if len(a[1]) < 2:
            return

        if a[1][0] not in (250,):
            return

        self.message_id = a[1][1].split()[1].decode('utf-8')
        return


def sendmail(smtp_config, to_addr, from_addr, subject, body, **headers):
    if type(to_addr) in (str,):
        to_addr = [to_addr]

    msg = MIMEMultipart()

    msg.set_unixfrom('author')
    msg['To'] = ', '.join(map(lambda x: email.utils.formataddr(('', x)), to_addr))
    msg['From'] = email.utils.formataddr(('', from_addr))
    msg['Subject'] = subject

    for k, v in headers.items():
        msg[k] = v

    #msg.attach(MIMEText(body, 'html; charset="utf-8"'))
    msg.attach(MIMEText(body, 'plain'))

    log.debug('''email message was formed:
-x--------------------------------------------------------------------------------
%s
--------------------------------------------------------------------------------x-''', msg.as_string())

    server = SMTP(smtp_config['host'], smtp_config['port'])
    server.set_debuglevel(2)

    try:
        server.ehlo()
        if server.has_extn('STARTTLS'):
            server.starttls()
            server.ehlo()

        if server.has_extn('AUTH'):
            server.login(smtp_config['user'], smtp_config['password'])

        server.sendmail(from_addr, to_addr, msg.as_string())
    except smtplib.SMTPResponseException:
        traceback.print_exc()
        return None
    finally:
        server.quit()

    return dict(
        message_id=server.message_id,
    )
