# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'BugEmailCommands',
    ]

import os

from lazr.lifecycle.event import (
    ObjectCreatedEvent,
    ObjectModifiedEvent,
    )
from lazr.lifecycle.interfaces import (
    IObjectCreatedEvent,
    IObjectModifiedEvent,
    )
from lazr.lifecycle.snapshot import Snapshot
from zope.component import getUtility
from zope.event import notify
from zope.interface import (
    implements,
    providedBy,
    )
from zope.schema.interfaces import (
    TooLong,
    ValidationError,
    )

from lp.app.enums import (
    InformationType,
    PUBLIC_INFORMATION_TYPES,
    )
from lp.app.errors import (
    NotFoundError,
    UserCannotUnsubscribePerson,
    )
from lp.app.validators.name import valid_name
from lp.bugs.interfaces.bug import (
    CreateBugParams,
    IBug,
    IBugAddForm,
    IBugSet,
    )
from lp.bugs.interfaces.bugtarget import ISeriesBugTarget
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    IBugTask,
    IllegalTarget,
    )
from lp.bugs.interfaces.cve import ICveSet
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.services.mail.commands import (
    EditEmailCommand,
    EmailCommand,
    EmailCommandCollection,
    )
from lp.services.mail.helpers import (
    get_error_message,
    get_person_or_team,
    )
from lp.services.mail.interfaces import (
    BugTargetNotFound,
    EmailProcessingError,
    IBugEditEmailCommand,
    IBugEmailCommand,
    IBugTaskEditEmailCommand,
    IBugTaskEmailCommand,
    )
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.interfaces import ILaunchBag


error_templates = os.path.join(os.path.dirname(__file__), 'errortemplates')


class BugEmailCommand(EmailCommand):
    """Creates new bug, or returns an existing one."""
    implements(IBugEmailCommand)

    _numberOfArguments = 1
    RANK = 0

    def execute(self, parsed_msg, filealias):
        """See IBugEmailCommand."""
        self._ensureNumberOfArguments()
        bugid = self.string_args[0]

        if bugid == 'new':
            message = getUtility(IMessageSet).fromEmail(
                parsed_msg.as_string(),
                owner=getUtility(ILaunchBag).user,
                filealias=filealias,
                parsed_message=parsed_msg)
            description = message.text_contents
            if description.strip() == '':
                # The report for a new bug must contain an affects command,
                # since the bug must have at least one task
                raise EmailProcessingError(
                    get_error_message(
                        'no-affects-target-on-submit.txt',
                        error_templates=error_templates),
                    stop_processing=True)

            # Check the message validator.
            validator = IBugAddForm['comment'].validate
            try:
                validator(description)
            except TooLong:
                raise EmailProcessingError(
                    'The description is too long. If you have lots of '
                    'text to add, use an attachment instead.',
                    stop_processing=True)
            except ValidationError as e:
                # More a just in case than any real expectation of getting
                # something.
                raise EmailProcessingError(
                    str(e),
                    stop_processing=True)

            params = CreateBugParams(
                msg=message, title=message.title,
                owner=getUtility(ILaunchBag).user)
            return params, None
        else:
            try:
                bugid = int(bugid)
            except ValueError:
                raise EmailProcessingError(
                    get_error_message(
                        'bug-argument-mismatch.txt',
                        error_templates=error_templates))

            try:
                bug = getUtility(IBugSet).get(bugid)
            except NotFoundError:
                bug = None
            if bug is None or not check_permission('launchpad.View', bug):
                raise EmailProcessingError(
                    get_error_message(
                        'no-such-bug.txt',
                        error_templates=error_templates,
                        bug_id=bugid))
            return bug, None


class PrivateEmailCommand(EmailCommand):
    """Marks a bug public or private.

    We do not subclass `EditEmailCommand` because we must call
    `IBug.setPrivate` to update privacy settings, rather than just
    updating an attribute.
    """

    implements(IBugEditEmailCommand)

    _numberOfArguments = 1
    RANK = 3

    def execute(self, context, current_event):
        """See `IEmailCommand`. Much of this method has been lifted from
        `EditEmailCommand.execute`.
        """
        # Parse args.
        self._ensureNumberOfArguments()
        private_arg = self.string_args[0]
        if private_arg == 'yes':
            private = True
        elif private_arg == 'no':
            private = False
        else:
            raise EmailProcessingError(
                get_error_message(
                    'private-parameter-mismatch.txt',
                    error_templates=error_templates),
                stop_processing=True)

        if isinstance(context, CreateBugParams):
            if private:
                # "private yes" forces it to Private if it isn't already.
                if (context.information_type is None
                    or context.information_type in PUBLIC_INFORMATION_TYPES):
                    context.information_type = InformationType.USERDATA
            elif context.information_type != InformationType.PRIVATESECURITY:
                # "private no" forces it to Public, except we always
                # force new security bugs to be private.
                context.information_type = InformationType.PUBLIC
            return context, current_event

        # Snapshot.
        edited_fields = set()
        if IObjectModifiedEvent.providedBy(current_event):
            context_snapshot = current_event.object_before_modification
            edited_fields.update(current_event.edited_fields)
        else:
            context_snapshot = Snapshot(
                context, providing=providedBy(context))

        # Apply requested changes.
        edited = context.setPrivate(private, getUtility(ILaunchBag).user)

        # Update the current event.
        if edited and not IObjectCreatedEvent.providedBy(current_event):
            edited_fields.add('private')
            current_event = ObjectModifiedEvent(
                context, context_snapshot, list(edited_fields))

        return context, current_event


class SecurityEmailCommand(EmailCommand):
    """Marks a bug as security related."""

    implements(IBugEditEmailCommand)

    _numberOfArguments = 1
    RANK = 2

    def execute(self, context, current_event):
        """See `IEmailCommand`.

        Much of this method was lifted from
        `EditEmailCommand.execute`.
        """
        # Parse args.
        self._ensureNumberOfArguments()
        [security_flag] = self.string_args
        if security_flag == 'yes':
            security_related = True
        elif security_flag == 'no':
            security_related = False
        else:
            raise EmailProcessingError(
                get_error_message(
                    'security-parameter-mismatch.txt',
                    error_templates=error_templates),
                stop_processing=True)

        if isinstance(context, CreateBugParams):
            if security_related:
                context.information_type = InformationType.PRIVATESECURITY
            return context, current_event

        # Take a snapshot.
        edited = False
        edited_fields = set()
        if IObjectModifiedEvent.providedBy(current_event):
            context_snapshot = current_event.object_before_modification
            edited_fields.update(current_event.edited_fields)
        else:
            context_snapshot = Snapshot(
                context, providing=providedBy(context))

        # Apply requested changes.
        user = getUtility(ILaunchBag).user
        if security_related:
            if context.setPrivate(True, user):
                edited = True
                edited_fields.add('private')
        if context.security_related != security_related:
            context.setSecurityRelated(security_related, user)
            edited = True
            edited_fields.add('security_related')

        # Update the current event.
        if edited and not IObjectCreatedEvent.providedBy(current_event):
            current_event = ObjectModifiedEvent(
                context, context_snapshot, list(edited_fields))

        return context, current_event


class SubscribeEmailCommand(EmailCommand):
    """Subscribes someone to the bug."""

    implements(IBugEditEmailCommand)
    RANK = 7

    def execute(self, bug, current_event):
        """See IEmailCommand."""
        string_args = list(self.string_args)
        # preserve compatibility with the original command that let you
        # specify a subscription type
        if len(string_args) == 2:
            # Remove the subscription_name
            string_args.pop()

        user = getUtility(ILaunchBag).user

        if len(string_args) == 1:
            person = get_person_or_team(string_args.pop())
        elif len(string_args) == 0:
            # Subscribe the sender of the email.
            person = user
        else:
            raise EmailProcessingError(
                get_error_message(
                    'subscribe-too-many-arguments.txt',
                    error_templates=error_templates))

        if isinstance(bug, CreateBugParams):
            if len(bug.subscribers) == 0:
                bug.subscribers = [person]
            else:
                bug.subscribers.append(person)
            return bug, current_event

        if bug.isSubscribed(person):
            # but we still need to find the subscription
            for bugsubscription in bug.subscriptions:
                if bugsubscription.person == person:
                    break

        else:
            bugsubscription = bug.subscribe(person, user)
            notify(ObjectCreatedEvent(bugsubscription))

        return bug, current_event


class UnsubscribeEmailCommand(EmailCommand):
    """Unsubscribes someone from the bug."""

    implements(IBugEditEmailCommand)
    RANK = 8

    def execute(self, bug, current_event):
        """See IEmailCommand."""
        if isinstance(bug, CreateBugParams):
            # Return the input because there is not yet a bug to
            # unsubscribe too.
            return bug, current_event

        string_args = list(self.string_args)
        if len(string_args) == 1:
            person = get_person_or_team(string_args.pop())
        elif len(string_args) == 0:
            # Subscribe the sender of the email.
            person = getUtility(ILaunchBag).user
        else:
            raise EmailProcessingError(
                get_error_message(
                    'unsubscribe-too-many-arguments.txt',
                    error_templates=error_templates))

        if bug.isSubscribed(person):
            try:
                bug.unsubscribe(person, getUtility(ILaunchBag).user)
            except UserCannotUnsubscribePerson:
                raise EmailProcessingError(
                    get_error_message(
                        'user-cannot-unsubscribe.txt',
                        error_templates=error_templates,
                        person=person.displayname))
        if bug.isSubscribedToDupes(person):
            bug.unsubscribeFromDupes(person, person)

        return bug, current_event


class SummaryEmailCommand(EditEmailCommand):
    """Changes the title of the bug."""

    implements(IBugEditEmailCommand)
    _numberOfArguments = 1
    RANK = 1
    case_insensitive_args = False

    def execute(self, bug, current_event):
        """See IEmailCommand."""
        if bug is None:
            raise EmailProcessingError(
                get_error_message(
                    'command-with-no-bug.txt',
                    error_templates=error_templates),
                stop_processing=True)

        # Do a manual control of the number of arguments, in order to
        # provide a better error message than the default one.
        if len(self.string_args) > 1:
            raise EmailProcessingError(
                get_error_message(
                    'summary-too-many-arguments.txt',
                    error_templates=error_templates))

        if isinstance(bug, CreateBugParams):
            bug.title = self.string_args[0]
            return bug, current_event

        return EditEmailCommand.execute(self, bug, current_event)

    def convertArguments(self, context):
        """See EmailCommand."""
        return {'title': self.string_args[0]}


class DuplicateEmailCommand(EmailCommand):
    """Marks a bug as a duplicate of another bug."""

    implements(IBugEditEmailCommand)
    _numberOfArguments = 1
    RANK = 6

    def execute(self, context, current_event):
        """See IEmailCommand."""
        if isinstance(context, CreateBugParams):
            # No one intentially reports a duplicate bug. Bug email commands
            # support CreateBugParams, so in this case, just return.
            return context, current_event
        self._ensureNumberOfArguments()
        [bug_id] = self.string_args

        if bug_id != 'no':
            try:
                bug = getUtility(IBugSet).getByNameOrID(bug_id)
            except NotFoundError:
                raise EmailProcessingError(
                    get_error_message(
                        'no-such-bug.txt',
                        error_templates=error_templates,
                        bug_id=bug_id))
        else:
            # 'no' is a special value for unmarking a bug as a duplicate.
            bug = None

        duplicate_field = IBug['duplicateof'].bind(context)
        try:
            duplicate_field.validate(bug)
        except ValidationError as error:
            raise EmailProcessingError(error.doc())

        context_snapshot = Snapshot(
            context, providing=providedBy(context))
        context.markAsDuplicate(bug)
        current_event = ObjectModifiedEvent(
            context, context_snapshot, 'duplicateof')
        notify(current_event)
        return bug, current_event


class CVEEmailCommand(EmailCommand):
    """Links a CVE to a bug."""

    implements(IBugEditEmailCommand)

    _numberOfArguments = 1
    RANK = 5
    case_insensitive_args = False

    def execute(self, bug, current_event):
        """See IEmailCommand."""
        [cve_sequence] = self.string_args
        cve = getUtility(ICveSet)[cve_sequence]
        if cve is None:
            raise EmailProcessingError(
                'Launchpad can\'t find the CVE "%s".' % cve_sequence)
        if isinstance(bug, CreateBugParams):
            bug.cve = cve
            return bug, current_event

        bug.linkCVE(cve, getUtility(ILaunchBag).user)
        return bug, current_event


class AffectsEmailCommand(EmailCommand):
    """Either creates a new task, or edits an existing task."""

    implements(IBugTaskEmailCommand)
    _numberOfArguments = 1
    RANK = 0

    @classmethod
    def _splitPath(cls, path):
        """Split the path part into two.

        The first part is the part before any slash, and the other is
        the part behind the slash.
        """
        if '/' not in path:
            return path, ''
        else:
            return tuple(path.split('/', 1))

    @classmethod
    def _normalizePath(cls, path):
        """Normalize the path.

        Previously the path had to start with either /distros/ or
        /products/. Simply remove any such prefixes to stay backward
        compatible.
        """
        for prefix in ['/distros/', '/products/', '/']:
            if path.startswith(prefix):
                path = path[len(prefix):]
                break
        return path

    @classmethod
    def getBugTarget(cls, path):
        """Return the IBugTarget with the given path.

        Path should be in any of the following forms:

            $product
            $product/$product_series
            $distribution
            $distribution/$source_package
            $distribution/$distro_series
            $distribution/$distro_series/$source_package
        """
        path = cls._normalizePath(path)
        name, rest = cls._splitPath(path)
        pillar = getUtility(IPillarNameSet).getByName(
            name, ignore_inactive=True)
        if pillar is None:
            raise BugTargetNotFound(
                "There is no project named '%s' registered in Launchpad." %
                    name)

        # We can't check for IBugTarget, since ProjectGroup is an IBugTarget
        # we don't allow bugs to be filed against.
        if IProjectGroup.providedBy(pillar):
            products = ", ".join(product.name for product in pillar.products)
            raise BugTargetNotFound(
                "%s is a group of projects. To report a bug, you need to"
                " specify which of these projects the bug applies to: %s" % (
                    pillar.name, products))
        assert IDistribution.providedBy(pillar) or IProduct.providedBy(pillar)

        if not rest:
            return pillar
        # Resolve the path that is after the pillar name.
        if IProduct.providedBy(pillar):
            series_name, rest = cls._splitPath(rest)
            product_series = pillar.getSeries(series_name)
            if product_series is None:
                raise BugTargetNotFound(
                    "%s doesn't have a series named '%s'." % (
                        pillar.displayname, series_name))
            elif not rest:
                return product_series
        else:
            assert IDistribution.providedBy(pillar)
            # The next step can be either a distro series or a source
            # package.
            series_name, rest = cls._splitPath(rest)
            try:
                series = pillar.getSeries(series_name)
            except NotFoundError:
                package_name = series_name
            else:
                if not rest:
                    return series
                else:
                    pillar = series
                    package_name, rest = cls._splitPath(rest)
            package = pillar.getSourcePackage(package_name)
            if package is None:
                raise BugTargetNotFound(
                    "%s doesn't have a series or source package named '%s'."
                    % (pillar.displayname, package_name))
            elif not rest:
                return package

        assert rest, "This is the fallback for unexpected path components."
        raise BugTargetNotFound("Unexpected path components: %s" % rest)

    def execute(self, bug, bug_event):
        """See IEmailCommand."""
        if bug is None:
            raise EmailProcessingError(
                get_error_message(
                    'command-with-no-bug.txt',
                    error_templates=error_templates),
                stop_processing=True)

        string_args = list(self.string_args)
        try:
            path = string_args.pop(0)
        except IndexError:
            raise EmailProcessingError(
                get_error_message(
                    'affects-no-arguments.txt',
                    error_templates=error_templates),
                stop_processing=True)
        try:
            bug_target = self.getBugTarget(path)
        except BugTargetNotFound as error:
            raise EmailProcessingError(unicode(error), stop_processing=True)
        event = None

        if isinstance(bug, CreateBugParams):
            # Enough information has been gathered to create a new bug.
            # If a series task is requested, create the non-series
            # equivalent here. The series will be nominated/targeted in
            # the remainder of the method.
            if ISeriesBugTarget.providedBy(bug_target):
                bug.target = bug_target.bugtarget_parent
            else:
                bug.target = bug_target
            bug, bug_event = getUtility(IBugSet).createBug(
                bug, notify_event=False)
            event = ObjectCreatedEvent(bug.bugtasks[0])
            # Continue because the bug_target may be a subordinate bugtask.

        bugtask = bug.getBugTask(bug_target)
        if (bugtask is None and
            IDistributionSourcePackage.providedBy(bug_target)):
            # If there's a distribution task with no source package, use
            # that one.
            bugtask = bug.getBugTask(bug_target.distribution)
            if bugtask is not None:
                bugtask_before_edit = Snapshot(
                    bugtask, providing=IBugTask)
                bugtask.transitionToTarget(
                    bug_target, getUtility(ILaunchBag).user)
                event = ObjectModifiedEvent(
                    bugtask, bugtask_before_edit, ['sourcepackagename'])

        if bugtask is None:
            try:
                bugtask = self._create_bug_task(bug, bug_target)
            except IllegalTarget as e:
                raise EmailProcessingError(
                    get_error_message(
                        'cannot-add-task.txt',
                        error_templates=error_templates,
                        bug_id=bug.id,
                        target_name=bug_target.name, reason=e[0]),
                    stop_processing=True)
            event = ObjectCreatedEvent(bugtask)

        return bugtask, event, bug_event

    def _targetBug(self, user, bug, target):
        """Try to target the bug the given distroseries.

        If the user doesn't have permission to target the bug directly,
        only a nomination will be created.
        """
        general_target = target.bugtarget_parent
        general_task = bug.getBugTask(general_target)
        if general_task is None:
            # A series task has to have a corresponding
            # distribution/product task.
            general_task = bug.addTask(user, general_target)

        # We know the target is of the right type, and we just created
        # a pillar task, so if canBeNominatedFor == False then a task or
        # nomination must already exist.
        if not bug.canBeNominatedFor(target.series):
            # A nomination has already been created.
            nomination = bug.getNominationFor(target.series)
        else:
            nomination = bug.addNomination(target=target.series, owner=user)

        # Automatically approve an existing or new nomination if possible.
        if not nomination.isApproved() and nomination.canApprove(user):
            nomination.approve(user)

        if nomination.isApproved():
            return bug.getBugTask(target)
        else:
            # We can't return a nomination, so return the
            # distribution/product bugtask instead.
            return general_task

    def _create_bug_task(self, bug, bug_target):
        """Creates a new bug task with bug_target as the target."""
        user = getUtility(ILaunchBag).user
        if ISeriesBugTarget.providedBy(bug_target):
            return self._targetBug(user, bug, bug_target)
        else:
            return bug.addTask(user, bug_target)


class AssigneeEmailCommand(EditEmailCommand):
    """Assigns someone to the bug."""

    implements(IBugTaskEditEmailCommand)

    _numberOfArguments = 1
    RANK = 2

    def convertArguments(self, context):
        """See EmailCommand."""
        person_name_or_email = self.string_args[0]

        # "nobody" is a special case that means assignee == None.
        if person_name_or_email == "nobody":
            return {self.name: None}

        return {self.name: get_person_or_team(person_name_or_email)}

    def setAttributeValue(self, context, attr_name, attr_value):
        """See EmailCommand."""
        context.transitionToAssignee(attr_value)


class MilestoneEmailCommand(EditEmailCommand):
    """Sets the milestone for the bugtask."""

    implements(IBugTaskEditEmailCommand)

    _numberOfArguments = 1
    RANK = 3

    def convertArguments(self, context):
        """See EmailCommand."""
        user = getUtility(ILaunchBag).user
        milestone_name = self.string_args[0]

        if milestone_name == '-':
            # Remove milestone
            return {self.name: None}
        elif context.userHasBugSupervisorPrivileges(user):
            milestone = context.pillar.getMilestone(milestone_name)
            if milestone is None:
                raise EmailProcessingError(
                    "The milestone %s does not exist for %s. Note that "
                    "milestones are not automatically created from emails; "
                    "they must be created on the website." % (
                        milestone_name, context.pillar.title))
            else:
                return {self.name: milestone}
        else:
            raise EmailProcessingError(
                "You do not have permission to set the milestone for %s. "
                "Only owners, drivers and bug supervisors may assign "
                "milestones." % (context.pillar.title,))


class DBSchemaEditEmailCommand(EditEmailCommand):
    """Helper class for edit DBSchema attributes.

    Subclasses should set 'dbschema' to the correct schema.

    For example, if context.foo can be assigned to values in
    FooDBSchema, the follwing command class could be created:

        class FooEmailCommand(DBSchemaEditEmailCommand):
            dbschema = FooDBSchema
    """

    implements(IBugTaskEditEmailCommand)

    _numberOfArguments = 1

    def convertArguments(self, context):
        """See EmailCommand."""
        item_name = self.string_args[0]
        dbschema = self.dbschema
        try:
            dbitem = dbschema.items[item_name.upper()]
        except KeyError:
            dbitem = None

        if dbitem is None or dbitem.name == 'UNKNOWN':
            possible_items = [
                item.name.lower() for item in dbschema.items
                if item.name != 'UNKNOWN']
            possible_values = ', '.join(possible_items)
            raise EmailProcessingError(
                    get_error_message(
                        'dbschema-command-wrong-argument.txt',
                         command_name=self.name,
                         arguments=possible_values,
                         example_argument=possible_items[0]))

        return {self.name: dbitem}


class InformationTypeEmailCommand(DBSchemaEditEmailCommand):
    """Change the information type of a bug."""

    implements(IBugEditEmailCommand)
    dbschema = InformationType
    RANK = 3

    def convertArguments(self, context):
        args = super(InformationTypeEmailCommand, self).convertArguments(
            context)
        return {'information_type': args['informationtype']}

    def setAttributeValue(self, context, attr_name, attr_value):
        """See EmailCommand."""
        user = getUtility(ILaunchBag).user
        if isinstance(context, CreateBugParams):
            context.information_type = attr_value
        else:
            context.transitionToInformationType(attr_value, user)


class StatusEmailCommand(DBSchemaEditEmailCommand):
    """Changes a bug task's status."""
    dbschema = BugTaskStatus
    RANK = 4

    def setAttributeValue(self, context, attr_name, attr_value):
        """See EmailCommand."""
        user = getUtility(ILaunchBag).user

        if not context.canTransitionToStatus(attr_value, user):
            raise EmailProcessingError(
                'The status cannot be changed to %s because you are not '
                'the maintainer, driver or bug supervisor for %s.' % (
                    attr_value.name.lower(), context.pillar.displayname))

        context.transitionToStatus(attr_value, user)


class ImportanceEmailCommand(DBSchemaEditEmailCommand):
    """Changes a bug task's importance."""
    dbschema = BugTaskImportance
    RANK = 5


class ReplacedByImportanceCommand(EmailCommand):
    """This command has been replaced by the 'importance' command."""
    implements(IBugTaskEditEmailCommand)
    RANK = 1

    def execute(self, context, current_event):
        raise EmailProcessingError(
                get_error_message(
                    'bug-importance.txt',
                    error_templates=error_templates,
                    argument=self.name))


class TagEmailCommand(EmailCommand):
    """Assigns a tag to or removes a tag from bug."""

    implements(IBugEditEmailCommand)
    RANK = 4

    def execute(self, bug, current_event):
        """See `IEmailCommand`."""
        # Tags are always lowercase.
        string_args = [arg.lower() for arg in self.string_args]
        if bug.tags is None:
            tags = []
        else:
            tags = list(bug.tags)
        for arg in string_args:
            # Are we adding or removing a tag?
            if arg.startswith('-'):
                remove = True
                tag = arg[1:]
            else:
                remove = False
                tag = arg
            # Tag must be a valid name.
            if not valid_name(tag):
                raise EmailProcessingError(
                    get_error_message(
                        'invalid-tag.txt',
                        error_templates=error_templates,
                        tag=tag))
            if remove:
                try:
                    tags.remove(tag)
                except ValueError:
                    raise EmailProcessingError(
                        get_error_message(
                            'unassigned-tag.txt',
                            error_templates=error_templates,
                            tag=tag))
            else:
                tags.append(arg)
        bug.tags = tags

        return bug, current_event


class BugEmailCommands(EmailCommandCollection):
    """A collection of email commands."""

    _commands = {
        'bug': BugEmailCommand,
        'informationtype': InformationTypeEmailCommand,
        'private': PrivateEmailCommand,
        'security': SecurityEmailCommand,
        'summary': SummaryEmailCommand,
        'subscribe': SubscribeEmailCommand,
        'unsubscribe': UnsubscribeEmailCommand,
        'duplicate': DuplicateEmailCommand,
        'cve': CVEEmailCommand,
        'affects': AffectsEmailCommand,
        'assignee': AssigneeEmailCommand,
        'milestone': MilestoneEmailCommand,
        'status': StatusEmailCommand,
        'importance': ImportanceEmailCommand,
        'severity': ReplacedByImportanceCommand,
        'priority': ReplacedByImportanceCommand,
        'tag': TagEmailCommand,
    }
