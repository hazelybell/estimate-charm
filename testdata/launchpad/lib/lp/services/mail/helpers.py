# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from cStringIO import StringIO as cStringIO
import os.path
import re
import time
from uuid import uuid1

from zope.component import getUtility

from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.mail.interfaces import (
    EmailProcessingError,
    IWeaklyAuthenticatedPrincipal,
    )
from lp.services.webapp import canonical_url
from lp.services.webapp.interaction import get_current_principal
from lp.services.webapp.interfaces import ILaunchBag


NO_KEY_TEMPLATE = 'key-not-registered.txt'
NOT_SIGNED_TEMPLATE = 'not-signed.txt'


class IncomingEmailError(Exception):
    """Indicates that something went wrong processing the mail."""

    def __init__(self, message, failing_command=None):
        Exception.__init__(self, message)
        self.message = message
        self.failing_command = failing_command


def get_main_body(signed_msg):
    """Returns the first text part of the email."""
    msg = getattr(signed_msg, 'signedMessage', None)
    if msg is None:
        # The email wasn't signed.
        msg = signed_msg
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                return part.get_payload(decode=True)
    else:
        return msg.get_payload(decode=True)


def guess_bugtask(bug, person):
    """Guess which bug task the person intended to edit.

    Return None if no bug task could be guessed.
    """
    if len(bug.bugtasks) == 1:
        return bug.bugtasks[0]
    else:
        for bugtask in bug.bugtasks:
            if bugtask.product:
                # Is the person an upstream maintainer?
                if person.inTeam(bugtask.product.owner):
                    return bugtask
            elif bugtask.distribution:
                # Is the person a member of the distribution?
                if person.inTeam(bugtask.distribution.members):
                    return bugtask
                else:
                    # Is the person one of the package subscribers?
                    bug_sub = bugtask.target.getSubscription(person)
                    if bug_sub is not None:
                        return bugtask
    return None


def reformat_wiki_text(text):
    """Transform moin formatted raw text to readable text."""

    # XXX Tom Berger 2008-02-20 bug=193646:
    # This implementation is neither correct nor complete.

    # Strip macros (anchors, TOC, etc'...)
    re_macro = re.compile('\[\[.*?\]\]')
    text = re_macro.sub('', text)

    # sterilize links
    re_link = re.compile('\[(.*?)\]')
    text = re_link.sub(
        lambda match: ' '.join(match.group(1).split(' ')[1:]), text)

    # Strip comments
    re_comment = re.compile('^#.*?$', re.MULTILINE)
    text = re_comment.sub('', text)

    return text


def parse_commands(content, command_names):
    """Extract indented commands from email body.

    All commands must be indented using either spaces or tabs.  They must be
    listed in command_names -- if not, they are silently ignored.

    The special command 'done' terminates processing.  It takes no arguments.
    Any commands that follow it will be ignored.  'done' should not be listed
    in command_names.

    While this syntax is the Launchpad standard, bug #29572 says it should be
    changed to only accept commands at the beginning and to not require
    indentation.

    A list of (command, args) tuples is returned.
    """
    commands = []

    for line in content.splitlines():
        # All commands have to be indented.
        if line.startswith(' ') or line.startswith('\t'):
            command_string = line.strip()
            if command_string == 'done':
                # If the 'done' statement is encountered,
                # stop reading any more commands.
                break
            words = command_string.split(' ', 1)
            if len(words) > 0:
                # Capitalization gets ignored
                first = words.pop(0).lower()
                if first.endswith(':'):
                    first = first[:-1]
                if first in command_names:
                    if len(words) > 0:
                        words = words[0]
                        if command_names[first]:
                            words = words.lower()
                        words = words.split(' ')
                    commands.append((first, words))
    return commands


def get_error_message(filename, error_templates=None, **interpolation_items):
    """Returns the error message that's in the given filename.

    If the error message requires some parameters, those are given in
    interpolation_items.

    The files are searched for in lib/lp.services/mail/errortemplates.
    """
    if error_templates is None:
        error_templates = os.path.join(
            os.path.dirname(__file__), 'errortemplates')
    fullpath = os.path.join(error_templates, filename)
    error_template = open(fullpath).read()
    return error_template % interpolation_items


def get_person_or_team(person_name_or_email):
    """Get the `Person` from the vocabulary.

    :raises: EmailProcessingError if person not found.
    """
    # Avoid circular import problems.
    from lp.registry.vocabularies import ValidPersonOrTeamVocabulary
    valid_person_vocabulary = ValidPersonOrTeamVocabulary()
    try:
        person_term = valid_person_vocabulary.getTermByToken(
            person_name_or_email)
    except LookupError:
        raise EmailProcessingError(
            get_error_message(
                'no-such-person.txt',
                name_or_email=person_name_or_email))
    return person_term.value


def ensure_not_weakly_authenticated(signed_msg, context,
                                    error_template='not-signed.txt'):
    """Make sure that the current principal is not weakly authenticated.

    NB: While handling an email, the authentication state is stored partly in
    properties of the message object, and partly in the current security
    principal.  As a consequence this function will only work correctly if the
    message has just been passed through authenticateEmail -- you can't give
    it an arbitrary message object.
    """
    cur_principal = get_current_principal()
    # The security machinery doesn't know about
    # IWeaklyAuthenticatedPrincipal yet, so do a manual
    # check. Later we can rely on the security machinery to
    # cause Unauthorized errors.
    if IWeaklyAuthenticatedPrincipal.providedBy(cur_principal):
        if signed_msg.signature is None:
            error_message = get_error_message(
                NOT_SIGNED_TEMPLATE, None, context=context)
        else:
            import_url = canonical_url(
                getUtility(ILaunchBag).user) + '/+editpgpkeys'
            error_message = get_error_message(
                NO_KEY_TEMPLATE, None, import_url=import_url, context=context)
        raise IncomingEmailError(error_message)


def ensure_sane_signature_timestamp(timestamp, context,
                                    error_template='old-signature.txt'):
    """Ensure the signature was generated recently but not in the future.

    If the timestamp is wrong, the message is rejected rather than just
    treated as untrusted, so that the user gets a chance to understand
    the problem.  Therefore, this raises an error rather than returning
    a value.

    :param context: Short user-readable description of the place
        the problem occurred.
    :raises IncomingEmailError: if the timestamp is stale or implausible,
        containing a message based on the context and template.
    """
    fourty_eight_hours = 48 * 60 * 60
    ten_minutes = 10 * 60
    now = time.time()
    fourty_eight_hours_ago = now - fourty_eight_hours
    ten_minutes_in_the_future = now + ten_minutes

    if (timestamp < fourty_eight_hours_ago
            or timestamp > ten_minutes_in_the_future):
        error_message = get_error_message(error_template, context=context)
        raise IncomingEmailError(error_message)


def save_mail_to_librarian(raw_mail, restricted=False):
    """Save the message to the librarian.

    It can be referenced from errors, and also accessed by code that needs to
    get back the exact original form.
    """
    # File the raw_mail in the Librarian.  We generate a filename to avoid
    # people guessing the URL.  We don't want URLs to private bug messages to
    # be guessable for example.
    file_name = str(uuid1()) + '.txt'
    file_alias = getUtility(ILibraryFileAliasSet).create(
        file_name, len(raw_mail), cStringIO(raw_mail), 'message/rfc822',
        restricted=restricted)
    return file_alias


def get_email_template(filename, app=None):
    """Returns the email template with the given file name.

    The templates are located in 'lib/canonical/launchpad/emailtemplates'.
    """
    if app is None:
        base = os.path.dirname(__file__)
        fullpath = os.path.join(base, 'emailtemplates', filename)
    else:
        import lp
        base = os.path.dirname(lp.__file__)
        fullpath = os.path.join(base, app, 'emailtemplates', filename)
    return open(fullpath).read()


def get_contact_email_addresses(person):
    """Return a set of email addresses to contact this Person.

    In general, it is better to use lp.registry.model.person.get_recipients
    instead.
    """
    # Need to remove the security proxy of the email address because the
    # logged in user may not have permission to see it.
    from zope.security.proxy import removeSecurityProxy
    # Circular imports force this import.
    from lp.registry.model.person import get_recipients
    return set(
        str(removeSecurityProxy(mail_person).preferredemail.email)
        for mail_person in get_recipients(person))
