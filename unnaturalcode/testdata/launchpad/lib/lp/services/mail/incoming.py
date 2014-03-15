# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functions dealing with mails coming into Launchpad."""

__metaclass__ = type

from cStringIO import StringIO as cStringIO
import email.errors
from email.utils import (
    getaddresses,
    parseaddr,
    )
import logging
import re
import sys

import dkim
import dns.exception
import transaction
from zope.component import getUtility
from zope.interface import (
    directlyProvidedBy,
    directlyProvides,
    )

from lp.registry.interfaces.person import IPerson
from lp.services.features import getFeatureFlag
from lp.services.gpg.interfaces import (
    GPGVerificationError,
    IGPGHandler,
    )
from lp.services.identity.interfaces.account import AccountStatus
from lp.services.identity.interfaces.emailaddress import (
    EmailAddressStatus,
    IEmailAddressSet,
    )
from lp.services.librarian.interfaces.client import UploadFailed
from lp.services.mail.handlers import mail_handlers
from lp.services.mail.helpers import (
    ensure_sane_signature_timestamp,
    get_error_message,
    IncomingEmailError,
    save_mail_to_librarian,
    )
from lp.services.mail.interfaces import IWeaklyAuthenticatedPrincipal
from lp.services.mail.mailbox import IMailBox
from lp.services.mail.notification import send_process_error_notification
from lp.services.mail.sendmail import do_paranoid_envelope_to_validation
from lp.services.mail.signedmessage import signed_message_from_string
from lp.services.webapp.errorlog import (
    ErrorReportingUtility,
    ScriptRequest,
    )
from lp.services.webapp.interaction import (
    get_current_principal,
    setupInteraction,
    )
from lp.services.webapp.interfaces import IPlacelessAuthUtility

# Match '\n' and '\r' line endings. That is, all '\r' that are not
# followed by a '\n', and all '\n' that are not preceded by a '\r'.
non_canonicalised_line_endings = re.compile('((?<!\r)\n)|(\r(?!\n))')

# Match trailing whitespace.
trailing_whitespace = re.compile(r'[ \t]*((?=\r\n)|$)')

# this is a hard limit on the size of email we will be willing to store in
# the database.
MAX_EMAIL_SIZE = 10 * 1024 * 1024


def canonicalise_line_endings(text):
    r"""Canonicalise the line endings to '\r\n'.

        >>> canonicalise_line_endings('\n\nfoo\nbar\rbaz\r\n')
        '\r\n\r\nfoo\r\nbar\r\nbaz\r\n'

        >>> canonicalise_line_endings('\r\rfoo\r\nbar\rbaz\n')
        '\r\n\r\nfoo\r\nbar\r\nbaz\r\n'

        >>> canonicalise_line_endings('\r\nfoo\r\nbar\nbaz\r')
        '\r\nfoo\r\nbar\r\nbaz\r\n'
    """
    if non_canonicalised_line_endings.search(text):
        text = non_canonicalised_line_endings.sub('\r\n', text)
    if trailing_whitespace.search(text):
        text = trailing_whitespace.sub('', text)
    return text


class InvalidSignature(Exception):
    """The signature failed to validate."""


class InactiveAccount(Exception):
    """The account for the person sending this email is inactive."""


_trusted_dkim_domains = [
    'gmail.com', 'google.com', 'mail.google.com', 'canonical.com']


def _isDkimDomainTrusted(domain):
    # Really this should come from a dynamically-modifiable
    # configuration, but we don't have such a thing yet.
    #
    # Being listed here means that we trust the domain not to be an open relay
    # or to allow arbitrary intra-domain spoofing.
    return domain in _trusted_dkim_domains


def _verifyDkimOrigin(signed_message):
    """Find a From or Sender address for which there's a DKIM signature.

    :returns: A string email address for the trusted sender, if there is one,
    otherwise None.

    :param signed_message: ISignedMessage
    """

    log = logging.getLogger('mail-authenticate-dkim')
    log.setLevel(logging.DEBUG)

    if getFeatureFlag('mail.dkim_authentication.disabled'):
        log.info('dkim authentication feature disabled')
        return None

    # uncomment this for easier test debugging
    # log.addHandler(logging.FileHandler('/tmp/dkim.log'))

    dkim_log = cStringIO()
    log.info(
        'Attempting DKIM authentication of message id=%r from=%r sender=%r'
        % (signed_message['Message-ID'],
           signed_message['From'],
           signed_message['Sender']))
    signing_details = []
    dkim_result = False
    try:
        dkim_result = dkim.verify(
            signed_message.parsed_string, dkim_log, details=signing_details)
    except dkim.DKIMException as e:
        log.warning('DKIM error: %r' % (e,))
    except dns.resolver.NXDOMAIN as e:
        # This can easily happen just through bad input data, ie claiming to
        # be signed by a domain with no visible key of that name.  It's not an
        # operational error.
        log.info('DNS exception: %r' % (e,))
    except dns.exception.DNSException as e:
        # many of them have lame messages, thus %r
        log.warning('DNS exception: %r' % (e,))
    except Exception as e:
        # DKIM leaks some errors when it gets bad input, as in bug 881237.  We
        # don't generally want them to cause the mail to be dropped entirely
        # though.  It probably is reasonable to treat them as potential
        # operational errors, at least until they're handled properly, by
        # making pydkim itself more defensive.
        log.warning(
            'unexpected error in DKIM verification, treating as unsigned: %r'
            % (e,))
    log.info('DKIM verification result: trusted=%s' % (dkim_result,))
    log.debug('DKIM debug log: %s' % (dkim_log.getvalue(),))
    if not dkim_result:
        return None
    # in addition to the dkim signature being valid, we have to check that it
    # was actually signed by the user's domain.
    if len(signing_details) != 1:
        log.info(
            'expected exactly one DKIM details record: %r'
            % (signing_details,))
        return None
    signing_domain = signing_details[0]['d']
    if not _isDkimDomainTrusted(signing_domain):
        log.info("valid DKIM signature from untrusted domain %s"
            % (signing_domain,))
        return None
    for origin in ['From', 'Sender']:
        if signed_message[origin] is None:
            continue
        name, addr = parseaddr(signed_message[origin])
        try:
            origin_domain = addr.split('@')[1]
        except IndexError:
            log.warning(
                "couldn't extract domain from address %r",
                signed_message[origin])
        if signing_domain == origin_domain:
            log.info(
                "DKIM signing domain %s matches %s address %r",
                signing_domain, origin, addr)
            return addr
    else:
        log.info("DKIM signing domain %s doesn't match message origin; "
            "disregarding signature"
            % (signing_domain))
        return None


def _getPrincipalByDkim(mail):
    """Determine the security principal from DKIM, if possible.

    To qualify:
        * there must be a dkim signature from a trusted domain
        * the From or Sender must be in that domain
        * the address in this header must be verified for a person

    :returns: (None, None), or (principal, trusted_addr).
    """
    log = logging.getLogger('mail-authenticate-dkim')
    authutil = getUtility(IPlacelessAuthUtility)

    dkim_trusted_address = _verifyDkimOrigin(mail)
    if dkim_trusted_address is None:
        return None, None

    log.debug('authenticated DKIM mail origin %s' % dkim_trusted_address)
    address = getUtility(IEmailAddressSet).getByEmail(dkim_trusted_address)
    if address is None:
        log.debug("valid dkim signature, but not from a known email address, "
            "therefore disregarding it")
        return None, None
    elif address.status not in (EmailAddressStatus.VALIDATED,
            EmailAddressStatus.PREFERRED):
        log.debug("valid dkim signature, "
            "but not from an active email address, "
            "therefore disregarding it")
        return None, None
    if address.person is None:
        log.debug("address is not associated with a person")
        return None, None
    account = address.person.account
    if account is None:
        log.debug("person does not have an account")
        return None, None
    dkim_principal = authutil.getPrincipal(account.id)
    return (dkim_principal, dkim_trusted_address)


def authenticateEmail(mail, signature_timestamp_checker=None):
    """Authenticates an email by verifying the PGP signature.

    The mail is expected to be an ISignedMessage.

    If this completes, it will set the current security principal to be the
    message sender.

    :param signature_timestamp_checker: This callable is
        passed the message signature timestamp, and it can raise an exception
        if it dislikes it (for example as a replay attack.)  This parameter is
        intended for use in tests.  If None, ensure_sane_signature_timestamp
        is used.
    """

    log = logging.getLogger('process-mail')
    authutil = getUtility(IPlacelessAuthUtility)

    principal, dkim_trusted_address = _getPrincipalByDkim(mail)
    if dkim_trusted_address is None:
        from_addr = parseaddr(mail['From'])[1]
        try:
            principal = authutil.getPrincipalByLogin(from_addr)
        except TypeError:
            # The email isn't valid, so don't authenticate
            principal = None

    if principal is None:
        setupInteraction(authutil.unauthenticatedPrincipal())
        return None

    person = IPerson(principal, None)
    if person.account_status != AccountStatus.ACTIVE:
        raise InactiveAccount(
            "Mail from a user with an inactive account.")

    if dkim_trusted_address:
        log.debug('accepting dkim strongly authenticated mail')
        setupInteraction(principal, dkim_trusted_address)
        return principal
    else:
        log.debug("attempt gpg authentication for %r" % person)
        return _gpgAuthenticateEmail(mail, principal, person,
            signature_timestamp_checker)


def _gpgAuthenticateEmail(mail, principal, person,
                          signature_timestamp_checker):
    """Check GPG signature.

    :param principal: Claimed sender of the mail; to be checked against
        the actual signature.
    :returns: principal, either strongly or weakly authenticated.
    """
    log = logging.getLogger('process-mail')
    signature = mail.signature
    email_addr = parseaddr(mail['From'])[1]
    if signature is None:
        # Mark the principal so that application code can check that the
        # user was weakly authenticated.
        log.debug('message has no signature; therefore weakly authenticated')
        directlyProvides(
            principal, directlyProvidedBy(principal),
            IWeaklyAuthenticatedPrincipal)
        setupInteraction(principal, email_addr)
        return principal

    gpghandler = getUtility(IGPGHandler)
    try:
        sig = gpghandler.getVerifiedSignature(
            canonicalise_line_endings(mail.signedContent), signature)
        log.debug("got signature %r" % sig)
    except GPGVerificationError as e:
        # verifySignature failed to verify the signature.
        message = "Signature couldn't be verified: %s" % e
        log.debug(message)
        raise InvalidSignature(message)

    if signature_timestamp_checker is None:
        signature_timestamp_checker = ensure_sane_signature_timestamp
    # If this fails, we return an error to the user rather than just treating
    # it as untrusted, so they can debug or understand the problem.
    signature_timestamp_checker(
        sig.timestamp,
        'incoming mail verification')

    for gpgkey in person.gpg_keys:
        if gpgkey.fingerprint == sig.fingerprint:
            log.debug('gpg-signed message by key %r' % gpgkey.fingerprint)
            break
    else:
        # The key doesn't belong to the user. Mark the principal so that the
        # application code knows that the key used to sign the email isn't
        # associated with the authenticated user.
        log.debug('gpg-signed message but by no known key of principal')
        directlyProvides(
            principal, directlyProvidedBy(principal),
            IWeaklyAuthenticatedPrincipal)

    setupInteraction(principal, email_addr)
    return principal


ORIGINAL_TO_HEADER = 'X-Launchpad-Original-To'


def extract_addresses(mail, file_alias_url, log):
    """Extract the domain the mail was sent to.

    Mails sent to Launchpad should have an X-Launchpad-Original-To header.
    This is added by the MTA before it ends up the mailbox for Launchpad.
    """
    if ORIGINAL_TO_HEADER in mail:
        return [mail[ORIGINAL_TO_HEADER]]

    if ORIGINAL_TO_HEADER in mail.as_string():
        # Doesn't have an X-Launchpad-Original-To in the headers, but does
        # have one in the body, because of a forwarding loop or attempted
        # spam.  See <https://bugs.launchpad.net/launchpad/+bug/701976>
        log.info('Suspected spam: %s' % file_alias_url)
    else:
        # This most likely means a email configuration problem, and it should
        # log an oops.
        log.warn(
            "No X-Launchpad-Original-To header was present "
            "in email: %s" % file_alias_url)
    # Process all addresses found as a fall back.
    cc = mail.get_all('cc') or []
    to = mail.get_all('to') or []
    names_addresses = getaddresses(to + cc)
    return [addr for name, addr in names_addresses]


def report_oops(file_alias_url=None, error_msg=None):
    """Record an OOPS for the current exception and return the OOPS ID."""
    info = sys.exc_info()
    properties = []
    if file_alias_url is not None:
        properties.append(('Sent message', file_alias_url))
    if error_msg is not None:
        properties.append(('Error message', error_msg))
    request = ScriptRequest(properties)
    request.principal = get_current_principal()
    errorUtility = ErrorReportingUtility()
    # Report all exceptions: the mail handling code doesn't expect any in
    # normal operation.
    errorUtility._ignored_exceptions = set()
    report = errorUtility.raising(info, request)
    # Note that this assert is arguably bogus: raising is permitted to filter
    # reports.
    assert report is not None, ('No OOPS generated.')
    return report['id']


def handleMail(trans=transaction, signature_timestamp_checker=None):

    log = logging.getLogger('process-mail')
    mailbox = getUtility(IMailBox)
    log.info("Opening the mail box.")
    mailbox.open()
    try:
        for mail_id, raw_mail in mailbox.items():
            log.info("Processing mail %s" % mail_id)
            trans.begin()
            try:
                file_alias = save_mail_to_librarian(raw_mail)
                # Let's save the url of the file alias, otherwise we might not
                # be able to access it later if we get a DB exception.
                file_alias_url = file_alias.http_url
                log.debug('Uploaded mail to librarian %s' % (file_alias_url,))
                # If something goes wrong when handling the mail, the
                # transaction will be aborted. Therefore we need to commit the
                # transaction now, to ensure that the mail gets stored in the
                # Librarian.
                trans.commit()
            except UploadFailed:
                # Something went wrong in the Librarian. It could be that it's
                # not running, but not necessarily. Log the error and skip the
                # message, but don't delete it: retrying might help.
                log.exception('Upload to Librarian failed')
                continue
            try:
                mail = signed_message_from_string(raw_mail)
            except email.Errors.MessageError:
                # If we can't parse the message, we can't send a reply back to
                # the user, but logging an exception will let us investigate.
                log.exception(
                    "Couldn't convert email to email.Message: %s" % (
                    file_alias_url, ))
                mailbox.delete(mail_id)
                continue
            try:
                trans.begin()
                handle_one_mail(log, mail, file_alias, file_alias_url,
                    signature_timestamp_checker)
                trans.commit()
                mailbox.delete(mail_id)
            except (KeyboardInterrupt, SystemExit):
                raise
            except:
                # This bare except is needed in order to prevent any bug
                # in the email handling from causing the email interface
                # to lock up. We simply log the error, then send an oops, and
                # continue through the mailbox, so that it doesn't stop the
                # rest of the emails from being processed.
                log.exception(
                    "An exception was raised inside the handler:\n%s"
                    % (file_alias_url,))
                # Delete the troublesome email before attempting to send the
                # OOPS in case something goes wrong.  Retrying probably
                # wouldn't work and we'd get stuck on the bad message.
                mailbox.delete(mail_id)
                _send_email_oops(trans, log, mail,
                    "Unhandled exception", file_alias_url)
    finally:
        log.info("Closing the mail box.")
        mailbox.close()


def _send_email_oops(trans, log, mail, error_msg, file_alias_url):
    """Handle an error that generates an oops.

    It does the following:
        * records an OOPS with error_msg and file_alias_url
        * commits the current transaction to ensure that the
            message gets sent
    """
    log.info('error processing mail: %s' % (error_msg,))
    oops_id = report_oops(
        file_alias_url=file_alias_url,
        error_msg=error_msg)
    log.info('oops %s' % (oops_id,))
    send_process_error_notification(
        mail['From'],
        'Submit Request Failure',
        get_error_message('oops.txt', oops_id=oops_id),
        mail)
    trans.commit()


def handle_one_mail(log, mail, file_alias, file_alias_url,
                    signature_timestamp_checker):
    """Process one message.

    Returns None when the message has either been successfully processed, or
    handled as a known error condition, in which case a reply will have been
    sent if appropriate.
    """
    log.debug('processing mail from %r message-id %r' %
        (mail['from'], mail['message-id']))

    # If the Return-Path header is '<>', it probably means
    # that it's a bounce from a message we sent.
    if mail['Return-Path'] == '<>':
        log.info("Message had an empty Return-Path.")
        return
    if mail.get_content_type() == 'multipart/report':
        # Mails with a content type of multipart/report are
        # generally DSN messages and should be ignored.
        log.info("Got a multipart/report message.")
        return
    if 'precedence' in mail:
        log.info("Got a message with a precedence header.")
        return

    if mail.raw_length > MAX_EMAIL_SIZE:
        complaint = (
            "The mail you sent to Launchpad is too long.\n\n"
            "Your message <%s>\nwas %d MB and the limit is %d MB." %
            (mail['message-id'], mail.raw_length / 1e6, MAX_EMAIL_SIZE / 1e6))
        log.info(complaint)
        # It's probably big and it's probably mostly binary, so trim it pretty
        # aggressively.
        send_process_error_notification(
            mail['From'], 'Mail to Launchpad was too large', complaint,
            mail, max_return_size=8192)
        return

    try:
        principal = authenticateEmail(mail, signature_timestamp_checker)
    except (InvalidSignature, IncomingEmailError) as error:
        send_process_error_notification(
            mail['From'], 'Submit Request Failure', str(error), mail)
        return
    except InactiveAccount:
        log.info("Inactive account found for %s" % mail['From'])
        return

    addresses = extract_addresses(mail, file_alias_url, log)
    log.debug('mail was originally to: %r' % (addresses,))

    try:
        do_paranoid_envelope_to_validation(addresses)
    except AssertionError as e:
        log.info("Invalid email address: %s" % e)
        return

    handler = None
    for email_addr in addresses:
        user, domain = email_addr.split('@')
        handler = mail_handlers.get(domain)
        if handler is not None:
            break
    else:
        raise AssertionError(
            "No handler registered for '%s' " % (', '.join(addresses)))

    if principal is None and not handler.allow_unknown_users:
        log.info('Mail from unknown users not permitted for this handler')
        return

    handled = handler.process(mail, email_addr, file_alias)
    if not handled:
        raise AssertionError("Handler found, but message was not handled")
