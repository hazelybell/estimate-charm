# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component.zcml import (
    handler,
    utility,
    )
from zope.interface import Interface
from zope.schema import (
    ASCII,
    Bool,
    )
from zope.sendmail.interfaces import IMailer
from zope.sendmail.zcml import IMailerDirective

from lp.services.mail.mailbox import (
    DirectoryMailBox,
    IMailBox,
    POP3MailBox,
    TestMailBox,
    )
from lp.services.mail.mbox import MboxMailer
from lp.services.mail.stub import (
    StubMailer,
    TestMailer,
    )


class ITestMailBoxDirective(Interface):
    """Configure a mail box which operates on test_emails."""


def testMailBoxHandler(_context):
    utility(_context, IMailBox, component=TestMailBox())


class IPOP3MailBoxDirective(Interface):
    """Configure a mail box which interfaces to a POP3 server."""
    host = ASCII(
            title=u"Host",
            description=u"Host name of the POP3 server.",
            required=True,
            )

    user = ASCII(
            title=u"User",
            description=u"User name to connect to the POP3 server with.",
            required=True,
            )

    password = ASCII(
            title=u"Password",
            description=u"Password to connect to the POP3 server with.",
            required=True,
            )

    ssl = Bool(
            title=u"SSL",
            description=u"Use SSL.",
            required=False,
            default=False)


def pop3MailBoxHandler(_context, host, user, password, ssl=False):
    utility(
        _context, IMailBox, component=POP3MailBox(host, user, password, ssl))


class IDirectoryMailBoxDirective(Interface):
    """Configure a mail box which interfaces to a directory of raw files."""
    directory = ASCII(
            title=u"Directory",
            description=u"The directory containing the raw mail files.",
            required=True,
            )


def directorymailBoxHandler(_context, directory):
    """Create the DirectoryMailBox and register the utility."""
    utility(_context, IMailBox, component=DirectoryMailBox(directory))


class IStubMailerDirective(IMailerDirective):
    from_addr = ASCII(
            title=u"From Address",
            description=u"All outgoing emails will use this email address",
            required=True,
            )
    to_addr = ASCII(
            title=u"To Address",
            description=(
                u"All outgoing emails will be redirected to this email "
                u"address"),
            required=True,
            )
    mailer = ASCII(
            title=u"Mailer to use",
            description=u"""\
                Which registered mailer to use, such as configured with
                the smtpMailer or sendmailMailer directives""",
                required=False,
                default='smtp',
                )
    rewrite = Bool(
            title=u"Rewrite headers",
            description=u"""\
                    If true, headers are rewritten in addition to the
                    destination address in the envelope. May me required
                    to bypass spam filters.""",
            required=False,
            default=False,
            )


def stubMailerHandler(_context, name, from_addr, to_addr,
                      mailer='smtp', rewrite=False):
    _context.action(
        discriminator=('utility', IMailer, name),
        callable=handler,
        args=('registerUtility',
                StubMailer(from_addr, [to_addr], mailer, rewrite),
                IMailer, name)
        )


class ITestMailerDirective(IMailerDirective):
    pass


def testMailerHandler(_context, name):
    _context.action(
        discriminator=('utility', IMailer, name),
        callable=handler,
        args=('registerUtility', TestMailer(), IMailer, name)
        )


class IMboxMailerDirective(IMailerDirective):
    filename = ASCII(
        title=u'File name',
        description=u'Unix mbox file to store outgoing emails in',
        required=True,
        )
    overwrite = Bool(
        title=u'Overwrite',
        description=u'Whether to overwrite the existing mbox file or not',
        required=False,
        default=False,
        )
    mailer = ASCII(
        title=u"Chained mailer to which messages are forwarded",
        description=u"""\
            Optional mailer to forward messages to, such as those configured
            with smtpMailer, sendmailMailer, or testMailer directives.  When
            not given, the message is not forwarded but only stored in the
            mbox file.""",
        required=False,
        default=None,
        )


def mboxMailerHandler(_context, name, filename, overwrite, mailer=None):
    _context.action(
        discriminator=('utility', IMailer, name),
        callable=handler,
        args=('registerUtility',
                MboxMailer(filename, overwrite, mailer),
                IMailer, name)
        )
