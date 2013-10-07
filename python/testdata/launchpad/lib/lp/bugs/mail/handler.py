# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Handle incoming Bugs email."""

__metaclass__ = type
__all__ = [
    "MaloneHandler",
    ]

from operator import attrgetter
import os

from lazr.lifecycle.event import ObjectCreatedEvent
from lazr.lifecycle.interfaces import IObjectCreatedEvent
import transaction
from zope.component import getUtility
from zope.event import notify
from zope.interface import implements

from lp.bugs.interfaces.bug import (
    CreateBugParams,
    CreatedBugWithNoBugTasksError,
    )
from lp.bugs.interfaces.bugattachment import (
    BugAttachmentType,
    IBugAttachmentSet,
    )
from lp.bugs.interfaces.bugmessage import IBugMessageSet
from lp.bugs.mail.commands import BugEmailCommands
from lp.services.identity.interfaces.emailaddress import IEmailAddressSet
from lp.services.mail.helpers import (
    ensure_not_weakly_authenticated,
    get_email_template,
    get_error_message,
    get_main_body,
    guess_bugtask,
    IncomingEmailError,
    parse_commands,
    reformat_wiki_text,
    )
from lp.services.mail.interfaces import (
    EmailProcessingError,
    IBugEditEmailCommand,
    IBugEmailCommand,
    IBugTaskEditEmailCommand,
    IBugTaskEmailCommand,
    IMailHandler,
    )
from lp.services.mail.mailwrapper import MailWrapper
from lp.services.mail.notification import send_process_error_notification
from lp.services.mail.sendmail import simple_sendmail
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.webapp.interfaces import ILaunchBag


error_templates = os.path.join(os.path.dirname(__file__), 'errortemplates')


class BugTaskCommandGroup:

    def __init__(self, command=None):
        self._commands = []
        if command is not None:
            self._commands.append(command)

    def __nonzero__(self):
        return len(self._commands) > 0

    def __str__(self):
        text_commands = [str(cmd) for cmd in self.commands]
        return '\n'.join(text_commands).strip()

    @property
    def commands(self):
        "Return the `EmailCommand`s ordered by their rank."
        return sorted(self._commands, key=attrgetter('RANK'))

    def add(self, command):
        "Add an `EmailCommand` to the commands."
        self._commands.append(command)


class BugCommandGroup(BugTaskCommandGroup):

    def __init__(self, command=None):
        super(BugCommandGroup, self).__init__(command=command)
        self._groups = []

    def __nonzero__(self):
        if len(self._groups) > 0:
            return True
        else:
            return super(BugCommandGroup, self).__nonzero__()

    def __str__(self):
        text_commands = [super(BugCommandGroup, self).__str__()]
        for group in self.groups:
            text_commands += [str(group)]
        return '\n'.join(text_commands).strip()

    @property
    def groups(self):
        "Return the `BugTaskCommandGroup`s."
        is_new_bug = (
            len(self.commands) > 0
            and self.commands[0].RANK == 0
            and self.commands[0].string_args == ['new'])
        has_split_affects = (
            len(self._groups) == 2
            and self._groups[0].commands[0].RANK != 0
            and self._groups[1].commands[0].RANK == 0)
        if is_new_bug and has_split_affects:
            # The affects line was in the wrong position and this
            # exact case can be fixed.
            self._groups[0]._commands += self._groups[1]._commands
            del self._groups[1]
        return list(self._groups)

    def add(self, command_or_group):
        """Add an `EmailCommand` or `BugTaskCommandGroup` to the commands.

        Empty BugTaskCommandGroup are ignored.
        """
        if isinstance(command_or_group, BugTaskCommandGroup):
            if command_or_group:
                self._groups.append(command_or_group)
        else:
            super(BugCommandGroup, self).add(command_or_group)


class BugCommandGroups(BugCommandGroup):

    def __init__(self, commands):
        super(BugCommandGroups, self).__init__(command=None)
        self._groups = []
        this_bug = BugCommandGroup()
        this_bugtask = BugTaskCommandGroup()
        for command in commands:
            if IBugEmailCommand.providedBy(command) and command.RANK == 0:
                # Multiple bugs are being edited.
                this_bug.add(this_bugtask)
                self.add(this_bug)
                this_bug = BugCommandGroup(command)
                this_bugtask = BugTaskCommandGroup()
            elif IBugEditEmailCommand.providedBy(command):
                this_bug.add(command)
            elif (IBugTaskEmailCommand.providedBy(command)
                  and command.RANK == 0):
                # Multiple or explicit bugtasks are being edited.
                this_bug.add(this_bugtask)
                this_bugtask = BugTaskCommandGroup(command)
            elif IBugTaskEditEmailCommand.providedBy(command):
                this_bugtask.add(command)
        this_bug.add(this_bugtask)
        self.add(this_bug)

    def __iter__(self):
        for bug_group in self.groups:
            for command in bug_group.commands:
                yield command
            for bugtask_group in bug_group.groups:
                for command in bugtask_group.commands:
                    yield command

    def add(self, command_or_group):
        """Add a `BugCommandGroup` to the groups of commands.

        Empty BugCommandGroups are ignored.
        """
        if isinstance(command_or_group, BugCommandGroup):
            if command_or_group:
                self._groups.append(command_or_group)


class MaloneHandler:
    """Handles emails sent to Malone.

    It only handles mail sent to new@... and $bugid@..., where $bugid is a
    positive integer.
    """
    implements(IMailHandler)

    allow_unknown_users = False

    def getCommands(self, signed_msg):
        """Returns a list of all the commands found in the email."""
        content = get_main_body(signed_msg)
        if content is None:
            return []
        return [
            BugEmailCommands.get(name=name, string_args=args) for
            name, args in parse_commands(
                content, BugEmailCommands.parsingParameters())]

    def extractAndAuthenticateCommands(self, signed_msg, to_addr):
        """Extract commands and handle special destinations.

        NB: The authentication is carried out against the current principal,
        not directly against the message.  authenticateEmail must previously
        have been called on this thread.

        :returns: (final_result, add_comment_to_bug, commands)
            If final_result is non-none, stop processing and return this value
            to indicate whether the message was dealt with or not.
            If add_comment_to_bug, add the contents to the first bug
            selected.
            commands is a list of bug commands.
        """
        CONTEXT = 'bug report'
        commands = self.getCommands(signed_msg)
        to_user, to_host = to_addr.split('@')
        add_comment_to_bug = False
        from_user = getUtility(ILaunchBag).user
        if to_user.lower() == 'help' or from_user is None:
            if from_user is not None and from_user.preferredemail is not None:
                to_address = str(from_user.preferredemail.email)
            else:
                to_address = signed_msg['From']
                address = getUtility(IEmailAddressSet).getByEmail(to_address)
                if address is None:
                    to_address = None
            if to_address is not None:
                self.sendHelpEmail(to_address)
            return True, False, None
        # If there are any commands, we must have strong authentication.
        # We send a different failure message for attempts to create a new
        # bug.
        elif to_user.lower() == 'new':
            ensure_not_weakly_authenticated(signed_msg, CONTEXT)
        elif len(commands) > 0:
            ensure_not_weakly_authenticated(signed_msg, CONTEXT)
        if to_user.lower() == 'new':
            commands.insert(0, BugEmailCommands.get('bug', ['new']))
        elif to_user.isdigit():
            # A comment to a bug. We set add_comment_to_bug to True so
            # that the comment gets added to the bug later. We don't add
            # the comment now, since we want to let the 'bug' command
            # handle the possible errors that can occur while getting
            # the bug.
            add_comment_to_bug = True
            commands.insert(0, BugEmailCommands.get('bug', [to_user]))
        elif to_user.lower() != 'edit':
            # Indicate that we didn't handle the mail.
            return False, False, None
        bug_commands = list(BugCommandGroups(commands))
        return None, add_comment_to_bug, bug_commands

    def process(self, signed_msg, to_addr, filealias=None, log=None):
        """See IMailHandler."""

        try:
            (final_result, add_comment_to_bug,
                commands, ) = self.extractAndAuthenticateCommands(
                    signed_msg, to_addr)
            if final_result is not None:
                return final_result

            bug = None
            bug_event = None
            bugtask = None
            bugtask_event = None

            processing_errors = []
            while len(commands) > 0:
                command = commands.pop(0)
                try:
                    if IBugEmailCommand.providedBy(command):
                        # Finish outstanding work from the previous bug.
                        self.notify_bug_event(bug_event)
                        self.notify_bugtask_event(bugtask_event, bug_event)
                        bugtask = None
                        bugtask_event = None
                        # Get or start building a new bug.
                        bug, bug_event = command.execute(signed_msg, filealias)
                        if add_comment_to_bug:
                            message = self.appendBugComment(
                                bug, signed_msg, filealias)
                            add_comment_to_bug = False
                            self.processAttachments(bug, message, signed_msg)
                    elif IBugTaskEmailCommand.providedBy(command):
                        self.notify_bugtask_event(bugtask_event, bug_event)
                        bugtask, bugtask_event, bug_event = command.execute(
                            bug, bug_event)
                        if isinstance(bug, CreateBugParams):
                            bug = bugtask.bug
                            message = bug.initial_message
                            self.processAttachments(bug, message, signed_msg)
                    elif IBugEditEmailCommand.providedBy(command):
                        bug, bug_event = command.execute(bug, bug_event)
                    elif IBugTaskEditEmailCommand.providedBy(command):
                        if bugtask is None:
                            if isinstance(bug, CreateBugParams):
                                self.handleNoAffectsTarget()
                            bugtask = guess_bugtask(
                                bug, getUtility(ILaunchBag).user)
                            if bugtask is None:
                                self.handleNoDefaultAffectsTarget(bug)
                        bugtask, bugtask_event = command.execute(
                            bugtask, bugtask_event)

                except EmailProcessingError as error:
                    processing_errors.append((error, command))
                    if error.stop_processing:
                        commands = []
                        transaction.abort()
                    else:
                        continue

            if len(processing_errors) > 0:
                raise IncomingEmailError(
                    '\n'.join(str(error) for error, command
                              in processing_errors),
                    [command for error, command in processing_errors])
            if isinstance(bug, CreateBugParams):
                # A new bug without any commands was sent.
                self.handleNoAffectsTarget()
            self.notify_bug_event(bug_event)
            self.notify_bugtask_event(bugtask_event, bug_event)

        except IncomingEmailError as error:
            send_process_error_notification(
                str(getUtility(ILaunchBag).user.preferredemail.email),
                'Submit Request Failure',
                error.message, signed_msg, error.failing_command)

        return True

    def sendHelpEmail(self, to_address):
        """Send usage help to `to_address`."""
        # Get the help text (formatted as MoinMoin markup)
        help_text = get_email_template('help.txt', app='bugs')
        help_text = reformat_wiki_text(help_text)
        # Wrap text
        mailwrapper = MailWrapper(width=72)
        help_text = mailwrapper.format(help_text)
        simple_sendmail(
            'help@bugs.launchpad.net', to_address,
            'Launchpad Bug Tracker Email Interface Help',
            help_text)

    # Some content types indicate that an attachment has a special
    # purpose. The current set is based on parsing emails from
    # one mail account and may need to be extended.
    #
    # Mail signatures are most likely generated by the mail client
    # and hence contain not data that is interesting except for
    # mail authentication.
    #
    # Resource forks of MacOS files are not easily represented outside
    # MacOS; if a resource fork contains useful debugging information,
    # the entire MacOS file should be sent encapsulated for example in
    # MacBinary format.
    #
    # application/ms-tnef attachment are created by Outlook; they
    # seem to store no more than an RTF representation of an email.

    irrelevant_content_types = set((
        'application/applefile',  # the resource fork of a MacOS file
        'application/pgp-signature',
        'application/pkcs7-signature',
        'application/x-pkcs7-signature',
        'text/x-vcard',
        'application/ms-tnef',
        ))

    def processAttachments(self, bug, message, signed_mail):
        """Create Bugattachments for "reasonable" mail attachments.

        A mail attachment is stored as a bugattachment if its
        content type is not listed in irrelevant_content_types.
        """
        for chunk in message.chunks:
            blob = chunk.blob
            if blob is None:
                continue
            # Mutt (other mail clients too?) appends the filename to the
            # content type.
            content_type = blob.mimetype.split(';', 1)[0]
            if content_type in self.irrelevant_content_types:
                continue

            if content_type == 'text/html' and blob.filename == 'unnamed':
                # This is the HTML representation of the main part of
                # an email.
                continue

            if content_type in ('text/x-diff', 'text/x-patch'):
                attach_type = BugAttachmentType.PATCH
            else:
                attach_type = BugAttachmentType.UNSPECIFIED

            getUtility(IBugAttachmentSet).create(
                bug=bug, filealias=blob, attach_type=attach_type,
                title=blob.filename, message=message, send_notifications=True)

    def appendBugComment(self, bug, signed_msg, filealias=None):
        """Append the message text to the bug comments."""
        messageset = getUtility(IMessageSet)
        message = messageset.fromEmail(
            signed_msg.as_string(), owner=getUtility(ILaunchBag).user,
            filealias=filealias, parsed_message=signed_msg,
            fallback_parent=bug.initial_message, restricted=bug.private)
        # If the new message's parent is linked to a bug watch we also link
        # this message to that bug watch.
        parent_bug_message = getUtility(IBugMessageSet).getByBugAndMessage(
            bug, message.parent)
        if (parent_bug_message is not None and
            parent_bug_message.bugwatch):
            bug_watch = parent_bug_message.bugwatch
        else:
            bug_watch = None
        bugmessage = bug.linkMessage(message, bug_watch)
        notify(ObjectCreatedEvent(bugmessage))
        return message

    def notify_bug_event(self, bug_event):
        if bug_event is  None:
            return
        try:
            notify(bug_event)
        except CreatedBugWithNoBugTasksError:
            self.handleNoAffectsTarget()

    def notify_bugtask_event(self, bugtask_event, bug_event):
            if bugtask_event is None:
                return
            if not IObjectCreatedEvent.providedBy(bug_event):
                notify(bugtask_event)

    def handleNoAffectsTarget(self):
        transaction.abort()
        raise IncomingEmailError(
            get_error_message(
                'no-affects-target-on-submit.txt',
                error_templates=error_templates))

    def handleNoDefaultAffectsTarget(self, bug):
        raise IncomingEmailError(get_error_message(
            'no-default-affects.txt',
            error_templates=error_templates,
            bug_id=bug.id,
            nr_of_bugtasks=len(bug.bugtasks)))
