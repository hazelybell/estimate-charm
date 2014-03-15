# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The One True Way to send mail from the Launchpad application.

Uses zope.sendmail.interfaces.IMailer, so you can subscribe to
IMailSentEvent or IMailErrorEvent to record status.

TODO: We should append a signature to messages sent through
simple_sendmail and sendmail with a message explaining 'this
came from launchpad' and a link to click on to change their
messaging settings -- stub 2004-10-21

"""

__all__ = [
    'append_footer',
    'do_paranoid_envelope_to_validation',
    'format_address',
    'format_address_for_person',
    'get_msgid',
    'MailController',
    'sendmail',
    'set_immediate_mail_delivery',
    'simple_sendmail',
    'simple_sendmail_from_person',
    'validate_message',
    ]


from binascii import b2a_qp
from email import Charset
from email.Encoders import encode_base64
from email.Header import Header
from email.Message import Message
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.Utils import (
    formataddr,
    formatdate,
    getaddresses,
    make_msgid,
    )
import hashlib
from smtplib import SMTP
import sys

from lazr.restful.utils import get_current_browser_request
from zope.component import getUtility
from zope.security.proxy import (
    isinstance as zisinstance,
    removeSecurityProxy,
    )
from zope.sendmail.interfaces import IMailDelivery

from lp.app import versioninfo
from lp.services.config import config
from lp.services.encoding import is_ascii_only
from lp.services.mail.stub import TestMailer
from lp.services.timeline.requesttimeline import get_request_timeline

# email package by default ends up encoding UTF-8 messages using base64,
# which sucks as they look like spam to stupid spam filters. We define
# our own custom charset definition to force quoted printable.
del Charset.CHARSETS['utf-8']
Charset.add_charset('utf-8', Charset.SHORTEST, Charset.QP, 'utf-8')
Charset.add_alias('utf8', 'utf-8')


def do_paranoid_email_content_validation(from_addr, to_addrs, subject, body):
    """Validate various bits of the email.

    Extremely paranoid parameter checking is required to ensure we
    raise an exception rather than stick garbage in the mail
    queue. Currently, the Z3 mailer is too forgiving and accepts badly
    formatted emails which the delivery mechanism then can't send.

    An AssertionError will be raised if one of the parameters is
    invalid.
    """
    # XXX StuartBishop 2005-03-19:
    # These checks need to be migrated upstream if this bug
    # still exists in modern Z3.
    assert zisinstance(from_addr, basestring), 'Invalid From: %r' % from_addr
    assert zisinstance(subject, basestring), 'Invalid Subject: %r' % subject
    assert zisinstance(body, basestring), 'Invalid body: %r' % body


def do_paranoid_envelope_to_validation(to_addrs):
    """Ensure the envelope_to addresses are valid.

    This is extracted from do_paranoid_email_content_validation, so that
    it can be applied to the actual envelope_to addresses, not the
    to header.  The to header and envelope_to addresses may vary
    independently, and the to header cannot break Z3.
    """
    assert (zisinstance(to_addrs, (list, tuple, set))
            and len(to_addrs) > 0), 'Invalid To: %r' % (to_addrs,)
    for addr in to_addrs:
        assert zisinstance(addr, basestring) and bool(addr), \
                'Invalid recipient: %r in %r' % (addr, to_addrs)
        assert '\n' not in addr, (
            "Address contains carriage returns: %r" % (addr,))


def append_footer(main, footer):
    """Append a footer to an email, following signature conventions.

    If there is no footer, do nothing.
    If there is already a signature, append an additional footer.
    If there is no existing signature, append '-- \n' and a footer.

    :param main: The main content, which may have a signature.
    :param footer: An additional footer to append.
    :return: a new version of main that includes the footer.
    """
    if footer == '':
        footer_separator = ''
    elif '\n-- \n' in main:
        footer_separator = '\n'
    else:
        footer_separator = '\n-- \n'
    return ''.join((main, footer_separator, footer))


def format_address(name, address):
    r"""Formats a name and address to be used as an email header.

        >>> format_address('Name', 'foo@bar.com')
        'Name <foo@bar.com>'
        >>> format_address('', 'foo@bar.com')
        'foo@bar.com'
        >>> format_address(None, u'foo@bar.com')
        'foo@bar.com'

    It handles unicode and characters that need quoting as well.

        >>> format_address(u'F\xf4\xf4 Bar', 'foo.bar@canonical.com')
        '=?utf-8?b?RsO0w7QgQmFy?= <foo.bar@canonical.com>'

        >>> format_address('Foo [Baz] Bar', 'foo.bar@canonical.com')
        '"Foo \\[Baz\\] Bar" <foo.bar@canonical.com>'

    Really long names doesn't get folded, since we're not constructing
    an e-mail header here.

        >>> formatted_address = format_address(
        ...     'a '*100, 'long.name@example.com')
        >>> '\n' in formatted_address
        False
    """
    if not name:
        return str(address)
    name = str(Header(name))
    # Using Header to encode the name has the side-effect that long
    # names are folded, so let's unfold it again.
    name = ''.join(name.splitlines())
    return str(formataddr((name, address)))


def format_address_for_person(person):
    """Helper function to call format_address for a person."""
    email_address = removeSecurityProxy(person.preferredemail).email
    return format_address(person.displayname, email_address)


_immediate_mail_delivery = False


def set_immediate_mail_delivery(enabled):
    """Enable or disable immediate mail delivery.

    Mail is by default queued until the transaction is committed. But if
    a script requires that mail violate transactions, immediate mail
    delivery can be enabled.
    """
    global _immediate_mail_delivery
    _immediate_mail_delivery = enabled


def simple_sendmail(from_addr, to_addrs, subject, body, headers=None,
                    bulk=True):
    """Send an email from from_addr to to_addrs with the subject and body
    provided. to_addrs can be a list, tuple, or ASCII string.

    Arbitrary headers can be set using the headers parameter. If the value for
    a given key in the headers dict is a list or tuple, the header will be
    added to the message once for each value in the list.

    Note however that the `Precedence` header will be set to `bulk` by
    default, overriding any `Precedence` header in `headers`.

    Returns the `Message-Id`.
    """
    ctrl = MailController(from_addr, to_addrs, subject, body, headers,
                          bulk=bulk)
    return ctrl.send()


class MailController(object):
    """Message generation interface closer to peoples' mental model."""

    def __init__(self, from_addr, to_addrs, subject, body, headers=None,
                 envelope_to=None, bulk=True):
        self.from_addr = from_addr
        if zisinstance(to_addrs, basestring):
            to_addrs = [to_addrs]
        self.to_addrs = to_addrs
        self.envelope_to = envelope_to
        self.subject = subject
        self.body = body
        if headers is None:
            headers = {}
        self.headers = headers
        self.bulk = bulk
        self.attachments = []

    def addAttachment(self, content, content_type='application/octet-stream',
                      inline=False, filename=None, charset=None):
        attachment = Message()
        if charset and isinstance(content, unicode):
            content = content.encode(charset)
        attachment.add_header('Content-Type', content_type)
        if inline:
            disposition = 'inline'
        else:
            disposition = 'attachment'
        disposition_kwargs = {}
        if filename is not None:
            disposition_kwargs['filename'] = filename
        attachment.add_header(
            'Content-Disposition', disposition, **disposition_kwargs)
        attachment.set_payload(content, charset)
        self.encodeOptimally(attachment)
        self.attachments.append(attachment)

    @staticmethod
    def encodeOptimally(part, exact=True):
        """Encode a message part as needed.

        If the part is more than 10% high-bit characters, it will be encoded
        using base64 encoding.  If the contents are 7-bit and exact is False,
        the part will not be encoded.  Otherwise, the message will be encoded
        as quoted-printable.

        If quoted-printable encoding is used, exact will cause all line-ending
        characters to be quoted.

        :param part: The message part to encode.
        :param exact: If True, the encoding will ensure newlines are not
            mangled.  If False, 7-bit attachments will not be encoded.
        """
        # If encoding has already been done by virtue of a charset being
        # previously specified, then do nothing.
        if 'Content-Transfer-Encoding' in part:
            return
        orig_payload = part.get_payload()
        if not exact and is_ascii_only(orig_payload):
            return
        # Payloads which are completely ascii need no encoding.
        quopri_bytes = b2a_qp(orig_payload, istext=not exact)
        # If 10% of characters need to be encoded, len is 1.2 times
        # the original len.  If more than 10% need encoding, the result
        # is unlikely to be readable.
        if len(quopri_bytes) < len(orig_payload) * 1.2:
            part.set_payload(quopri_bytes)
            part['Content-Transfer-Encoding'] = 'quoted-printable'
        else:
            encode_base64(part)

    def makeMessage(self):
        # It's the caller's responsibility to either encode the address fields
        # to ASCII strings or pass in Unicode strings.

        # Using the maxlinelen for the Headers as we have paranoid checks to
        # make sure that we have no carriage returns in the to or from email
        # addresses.  We use nice email addresses like 'Launchpad Community
        # Help Rotation team <long.email.address+devnull@example.com>' that
        # get broken over two lines in the header.  RFC 5322 specified that
        # the lines MUST be no more than 998, so we use that as our maximum.
        from_addr = Header(self.from_addr, maxlinelen=998).encode()
        to_addrs = [Header(address, maxlinelen=998).encode()
            for address in list(self.to_addrs)]

        for address in [from_addr] + to_addrs:
            if not isinstance(address, str) or not is_ascii_only(address):
                raise AssertionError(
                    'Expected an ASCII str object, got: %r' % address)

        do_paranoid_email_content_validation(
            from_addr=from_addr, to_addrs=to_addrs,
            subject=self.subject, body=self.body)
        if len(self.attachments) == 0:
            msg = MIMEText(self.body.encode('utf-8'), 'plain', 'utf-8')
        else:
            msg = MIMEMultipart()
            body_part = MIMEText(self.body.encode('utf-8'), 'plain', 'utf-8')
            msg.attach(body_part)
            for attachment in self.attachments:
                msg.attach(attachment)

        # The header_body_values may be a list or tuple of values, so we will
        # add a header once for each value provided for that header.
        # (X-Launchpad-Bug, for example, may often be set more than once for a
        # bugmail.)
        for header, header_body_values in self.headers.items():
            if not zisinstance(header_body_values, (list, tuple)):
                header_body_values = [header_body_values]
            for header_body_value in header_body_values:
                msg[header] = header_body_value
        msg['To'] = ','.join(to_addrs)
        msg['From'] = from_addr
        msg['Subject'] = self.subject
        return msg

    def send(self, bulk=True):
        return sendmail(self.makeMessage(), self.envelope_to, bulk=self.bulk)


def simple_sendmail_from_person(
    person, to_addrs, subject, body, headers=None):
    """Sends a mail using the given person as the From address.

    It works just like simple_sendmail, excepts that it ensures that the
    From header is properly encoded.
    """
    from zope.security.proxy import removeSecurityProxy
    # Bypass zope's security because IEmailAddress.email is not public.
    naked_email = removeSecurityProxy(person.preferredemail)
    from_addr = format_address(person.displayname, naked_email.email)
    return simple_sendmail(
        from_addr, to_addrs, subject, body, headers=headers)


def get_addresses_from_header(email_header):
    r"""Get the e-mail addresses specificed in an e-mail header.

        >>> get_addresses_from_header('one@example.com')
        ['one@example.com']
        >>> get_addresses_from_header('one@example.com, two@example.com')
        ['one@example.com', 'two@example.com']
        >>> get_addresses_from_header('One\n <one@example.com>')
        ['One <one@example.com>']
        >>> get_addresses_from_header('One\r\n <one@example.com>')
        ['One <one@example.com>']
        >>> get_addresses_from_header(
        ...     '"One, A" <one.a@example.com>,\n'
        ...     ' "Two, B" <two.b@example.com>')
        ['"One, A" <one.a@example.com>', '"Two, B" <two.b@example.com>']

    """
    return [
        formataddr((name, address))
        for name, address in getaddresses([email_header])]


def validate_message(message):
    """Validate that the supplied message is suitable for sending."""
    assert isinstance(message, Message), "Not an email.Message.Message"
    assert 'to' in message and bool(message['to']), "No To: header"
    assert 'from' in message and bool(message['from']), "No From: header"
    assert 'subject' in message and bool(message['subject']), (
            "No Subject: header")


def sendmail(message, to_addrs=None, bulk=True):
    """Send an email.Message.Message

    If you just need to send dumb ASCII or Unicode, simple_sendmail
    will be easier for you. Sending attachments or multipart messages
    will need to use this method.

    From:, To: and Subject: headers should already be set.
    Message-Id:, Date:, and Reply-To: headers will be set if they are
    not already. Errors-To: and Return-Path: headers will always be set.
    The more we look valid, the less we look like spam.

    If to_addrs is None, the message will be sent to all the addresses
    specified in the To: and CC: headers.

    Uses zope.sendmail.interfaces.IMailer, so you can subscribe to
    IMailSentEvent or IMailErrorEvent to record status.

    This function looks at the `config` singleton for configuration as to
    where to send the mail; in particular for whether this code is running in
    zopeless mode, and for a `sendmail_to_stdout` attribute for testing.

    :param bulk: By default, a Precedence: bulk header is added to the
        message. Pass False to disable this.

    Returns the Message-Id
    """
    validate_message(message)
    if to_addrs is None:
        to_addrs = get_addresses_from_header(message['to'])
        if message['cc']:
            to_addrs = to_addrs + get_addresses_from_header(message['cc'])

    do_paranoid_envelope_to_validation(to_addrs)

    # Add a Message-Id: header if it isn't already there
    if 'message-id' not in message:
        message['Message-Id'] = get_msgid()

    # Add a Date: header if it isn't already there
    if 'date' not in message:
        message['Date'] = formatdate()

    # Add a Reply-To: header if it isn't already there
    if 'reply-to' not in message:
        message['Reply-To'] = message['from']

    # Add a Sender: header to show that we were the one sending the
    # email.
    if "Sender" not in message:
        message["Sender"] = config.canonical.bounce_address

    # Add an Errors-To: header for bounce handling
    del message['Errors-To']
    message['Errors-To'] = config.canonical.bounce_address

    # Add a Return-Path: header for bounce handling as well. Normally
    # this is added by the SMTP mailer using the From: header. But we
    # want it to be bounce_address instead.
    if 'return-path' not in message:
        message['Return-Path'] = config.canonical.bounce_address

    if bulk:
        # Add Precedence header to prevent automatic reply programs
        # (e.g. vacation) from trying to respond to our messages.
        del message['Precedence']
        message['Precedence'] = 'bulk'

    # Add an X-Generated-By header for easy whitelisting
    del message['X-Generated-By']
    message['X-Generated-By'] = 'Launchpad (canonical.com)'
    message.set_param('Revision', str(versioninfo.revno), 'X-Generated-By')
    message.set_param('Instance', config.name, 'X-Generated-By')

    # Add a shared secret header for pre-approval with Mailman. This approach
    # helps security, but still exposes us to a replay attack; we consider the
    # risk low.
    del message['X-Launchpad-Hash']
    hash = hashlib.sha1(config.mailman.shared_secret)
    hash.update(str(message['message-id']))
    message['X-Launchpad-Hash'] = hash.hexdigest()

    raw_message = message.as_string()
    message_detail = message['Subject']
    if not isinstance(message_detail, basestring):
        # Might be a Header object; can be squashed.
        message_detail = unicode(message_detail)
    if _immediate_mail_delivery:
        # Immediate email delivery is not unit tested, and won't be.
        # The immediate-specific stuff is pretty simple though so this
        # should be fine.
        # TODO: Store a timeline action for immediate mail.

        if config.isTestRunner():
            # when running in the testing environment, store emails
            TestMailer().send(
                config.canonical.bounce_address, to_addrs, raw_message)
        elif getattr(config, 'sendmail_to_stdout', False):
            # For debugging, from process-one-mail, just print it.
            sys.stdout.write(raw_message)
        else:
            if config.immediate_mail.send_email:
                # Note that we simply throw away dud recipients. This is fine,
                # as it emulates the Z3 API which doesn't report this either
                # (because actual delivery is done later).
                smtp = SMTP(
                    config.immediate_mail.smtp_host,
                    config.immediate_mail.smtp_port)

                # The "MAIL FROM" is set to the bounce address, to behave in a
                # way similar to mailing list software.
                smtp.sendmail(
                    config.canonical.bounce_address, to_addrs, raw_message)
                smtp.quit()
        # Strip the angle brackets to the return a Message-Id consistent with
        # raw_sendmail (which doesn't include them).
        return message['message-id'][1:-1]
    else:
        # The "MAIL FROM" is set to the bounce address, to behave in a way
        # similar to mailing list software.
        return raw_sendmail(
            config.canonical.bounce_address,
            to_addrs,
            raw_message,
            message_detail)


def get_msgid():
    return make_msgid('launchpad')


def raw_sendmail(from_addr, to_addrs, raw_message, message_detail):
    """Send a raw RFC8222 email message.

    All headers and encoding should already be done, as the message is
    spooled out verbatim to the delivery agent.

    You should not need to call this method directly, although it may be
    necessary to pass on signed or encrypted messages.

    Returns the message-id.

    :param message_detail: String of detail about the message
        to be recorded to help with debugging, eg the message subject.
    """
    assert not isinstance(to_addrs, basestring), 'to_addrs must be a sequence'
    assert isinstance(raw_message, str), 'Not a plain string'
    assert raw_message.decode('ascii'), 'Not ASCII - badly encoded message'
    mailer = getUtility(IMailDelivery, 'Mail')
    request = get_current_browser_request()
    timeline = get_request_timeline(request)
    action = timeline.start("sendmail", message_detail)
    try:
        return mailer.send(from_addr, to_addrs, raw_message)
    finally:
        action.finish()
