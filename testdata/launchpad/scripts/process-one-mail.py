#!/usr/bin/python -S
#
# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Process one email message, read from stdin."""

import _pythonpath

import sys

from lp.services.config import config
from lp.services.mail.helpers import save_mail_to_librarian
from lp.services.mail.incoming import handle_one_mail
from lp.services.mail.signedmessage import signed_message_from_string
from lp.services.scripts.base import LaunchpadScript


class ProcessMail(LaunchpadScript):
    usage = """%prog [options] [MAIL_FILE]

    Process one incoming email, read from the specified file or from stdin.

    Any mail generated in response is printed to stdout.

    """ + __doc__

    def main(self):
        self.txn.begin()
        # NB: This somewhat duplicates handleMail, but there it's mixed in
        # with handling a mailbox, which we're avoiding here.
        if len(self.args) >= 1:
            from_file = file(self.args[0], 'rb')
        else:
            from_file = sys.stdin
        self.logger.debug("reading message from %r" % (from_file,))
        raw_mail = from_file.read()
        self.logger.debug("got %d bytes" % len(raw_mail))
        file_alias = save_mail_to_librarian(raw_mail)
        self.logger.debug("saved to librarian as %r" % (file_alias,))
        parsed_mail = signed_message_from_string(raw_mail)
        # Kinda kludgey way to cause sendmail to just print it.
        config.sendmail_to_stdout = True
        handle_one_mail(
            self.logger, parsed_mail,
            file_alias, file_alias.http_url,
            signature_timestamp_checker=None)
        self.logger.debug("mail handling complete")
        self.txn.commit()


if __name__ == '__main__':
    script = ProcessMail('process-one-mail', dbuser=config.processmail.dbuser)
    # No need to lock; you can run as many as you want as they use no global
    # resources (like a mailbox).
    script.run(use_web_security=True)
