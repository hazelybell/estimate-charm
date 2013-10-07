# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from doctest import DocTestSuite
import re

from zope.testing.renormalizing import RENormalizing

from lp.testing.layers import LaunchpadFunctionalLayer


def test_simple_sendmail():
    r"""
    Send an email (faked by TestMailer - no actual email is sent)

    >>> import email
    >>> from email.MIMEText import MIMEText
    >>> import transaction
    >>> from lp.services.mail import stub
    >>> from lp.services.mail.sendmail import simple_sendmail

    >>> body = 'The email body'
    >>> subject = 'The email subject'
    >>> message_id1 = simple_sendmail(
    ...     'nobody1@example.com', ['nobody2@example.com'], subject, body
    ...     )

    We should have a message id, a string

    >>> bool(message_id1)
    True
    >>> isinstance(message_id1,str)
    True

    We can also send arbitrary headers through. Note how Python's
    email package handles Message-Id headers

    >>> message_id2 = simple_sendmail(
    ...     'nobody@example.com', ['nobody2@example.com'], subject, body,
    ...     {'Message-Id': '<myMessageId>', 'X-Fnord': 'True'}
    ...     )
    >>> message_id2
    'myMessageId'

    The TestMailer stores sent emails in memory (which we cleared in the
    setUp() method). But the actual email has yet to be sent, as that
    happens when the transaction is committed.

    >>> len(stub.test_emails)
    0
    >>> transaction.commit()
    >>> len(stub.test_emails)
    2
    >>> stub.test_emails[0] == stub.test_emails[1]
    False

    We have two emails, but we have no idea what order they are in!

    Let's sort them, and verify that the first one is the one we want
    because only the first one contains the string 'nobody@example.com'
    in its raw message.

    >>> sorted_test_emails = sorted(list(stub.test_emails))
    >>> for from_addr, to_addrs, raw_message in sorted_test_emails:
    ...     print from_addr, to_addrs, 'nobody@example.com' in raw_message
    bounces@canonical.com ['nobody2@example.com'] True
    bounces@canonical.com ['nobody2@example.com'] False

    >>> from_addr, to_addrs, raw_message = sorted_test_emails[0]
    >>> from_addr
    'bounces@canonical.com'
    >>> to_addrs
    ['nobody2@example.com']

    The message should be a sane RFC2822 document

    >>> message = email.message_from_string(raw_message)
    >>> message['From']
    'nobody@example.com'
    >>> message['To']
    'nobody2@example.com'
    >>> message['Subject'] == subject
    True
    >>> message['Message-Id']
    '<myMessageId>'
    >>> message.get_payload() == body
    True

    Character set should be utf-8 as per Bug #39758. utf8 isn't good enough.

    >>> message['Content-Type']
    'text/plain; charset="utf-8"'

    And we want quoted printable, as it generally makes things readable
    and for languages it doesn't help, the only downside to base64 is bloat.

    >>> message['Content-Transfer-Encoding']
    'quoted-printable'

    The message has a number of additional headers added by default.
    'X-Generated-By' not only indicates that the source is Launchpad, but
    shows the bzr revision and instance name.

    >>> message['X-Generated-By'].replace('\n\t', '\n ')
    'Launchpad (canonical.com); Revision="1999";\n Instance="launchpad-lazr.conf"'

    """

def test_suite():
    suite = DocTestSuite(checker=RENormalizing([
        (re.compile(r'Revision="\d+"'), 'Revision="1999"')]))
    suite.layer = LaunchpadFunctionalLayer
    return suite
