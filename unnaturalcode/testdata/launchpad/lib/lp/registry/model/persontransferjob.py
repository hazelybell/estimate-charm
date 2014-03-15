# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Job classes related to PersonTransferJob."""

__metaclass__ = type
__all__ = [
    'MembershipNotificationJob',
    'PersonTransferJob',
    ]

from lazr.delegates import delegates
import simplejson
from storm.expr import (
    And,
    Or,
    )
from storm.locals import (
    Int,
    Reference,
    Unicode,
    )
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.enums import (
    PersonTransferJobType,
    TeamMembershipPolicy,
    )
from lp.registry.interfaces.person import (
    IPerson,
    IPersonSet,
    ITeam,
    )
from lp.registry.interfaces.persontransferjob import (
    IMembershipNotificationJob,
    IMembershipNotificationJobSource,
    IPersonDeactivateJob,
    IPersonDeactivateJobSource,
    IPersonMergeJob,
    IPersonMergeJobSource,
    IPersonTransferJob,
    IPersonTransferJobSource,
    )
from lp.registry.interfaces.teammembership import TeamMembershipStatus
from lp.registry.model.person import Person
from lp.registry.personmerge import merge_people
from lp.services.config import config
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.stormbase import StormBase
from lp.services.job.model.job import (
    EnumeratedSubclass,
    Job,
    )
from lp.services.job.runner import BaseRunnableJob
from lp.services.mail.helpers import (
    get_contact_email_addresses,
    get_email_template,
    )
from lp.services.mail.mailwrapper import MailWrapper
from lp.services.mail.sendmail import (
    format_address,
    format_address_for_person,
    simple_sendmail,
    )
from lp.services.webapp import canonical_url


class PersonTransferJob(StormBase):
    """Base class for team membership and person merge jobs."""

    implements(IPersonTransferJob)

    __storm_table__ = 'PersonTransferJob'

    id = Int(primary=True)

    job_id = Int(name='job')
    job = Reference(job_id, Job.id)

    major_person_id = Int(name='major_person')
    major_person = Reference(major_person_id, Person.id)

    minor_person_id = Int(name='minor_person')
    minor_person = Reference(minor_person_id, Person.id)

    job_type = EnumCol(enum=PersonTransferJobType, notNull=True)

    _json_data = Unicode('json_data')

    @property
    def metadata(self):
        return simplejson.loads(self._json_data)

    def __init__(self, minor_person, major_person, job_type, metadata,
                 requester=None):
        """Constructor.

        :param minor_person: The person or team being added to or removed
                             from the major_person.
        :param major_person: The person or team that is receiving or losing
                             the minor person.
        :param job_type: The specific membership action being performed.
        :param metadata: The type-specific variables, as a JSON-compatible
                         dict.
        """
        super(PersonTransferJob, self).__init__()
        self.job = Job(requester=requester)
        self.job_type = job_type
        self.major_person = major_person
        self.minor_person = minor_person

        json_data = simplejson.dumps(metadata)
        # XXX AaronBentley 2009-01-29 bug=322819: This should be a bytestring,
        # but the DB representation is unicode.
        self._json_data = json_data.decode('utf-8')

    def makeDerived(self):
        return PersonTransferJobDerived.makeSubclass(self)


class PersonTransferJobDerived(BaseRunnableJob):
    """Intermediate class for deriving from PersonTransferJob.

    Storm classes can't simply be subclassed or you can end up with
    multiple objects referencing the same row in the db. This class uses
    lazr.delegates, which is a little bit simpler than storm's
    infoheritance solution to the problem. Subclasses need to override
    the run() method.
    """

    __metaclass__ = EnumeratedSubclass
    delegates(IPersonTransferJob)
    classProvides(IPersonTransferJobSource)

    def __init__(self, job):
        self.context = job

    @classmethod
    def create(cls, minor_person, major_person, metadata, requester=None):
        """See `IPersonTransferJob`."""
        if not IPerson.providedBy(minor_person):
            raise TypeError("minor_person must be IPerson: %s"
                            % repr(minor_person))
        if not IPerson.providedBy(major_person):
            raise TypeError("major_person must be IPerson: %s"
                            % repr(major_person))
        job = PersonTransferJob(
            minor_person=minor_person,
            major_person=major_person,
            job_type=cls.class_job_type,
            metadata=metadata,
            requester=requester)
        derived = cls(job)
        derived.celeryRunOnCommit()
        return derived

    @classmethod
    def iterReady(cls):
        """Iterate through all ready PersonTransferJobs."""
        store = IMasterStore(PersonTransferJob)
        jobs = store.find(
            PersonTransferJob,
            And(PersonTransferJob.job_type == cls.class_job_type,
                PersonTransferJob.job_id.is_in(Job.ready_jobs)))
        return (cls(job) for job in jobs)

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = BaseRunnableJob.getOopsVars(self)
        vars.extend([
            ('major_person_name', self.context.major_person.name),
            ('minor_person_name', self.context.minor_person.name),
            ])
        return vars


class MembershipNotificationJob(PersonTransferJobDerived):
    """A Job that sends notifications about team membership changes."""

    implements(IMembershipNotificationJob)
    classProvides(IMembershipNotificationJobSource)

    class_job_type = PersonTransferJobType.MEMBERSHIP_NOTIFICATION

    config = config.IMembershipNotificationJobSource

    @classmethod
    def create(cls, member, team, reviewer, old_status, new_status,
               last_change_comment=None):
        if not ITeam.providedBy(team):
            raise TypeError('team must be ITeam: %s' % repr(team))
        if not IPerson.providedBy(reviewer):
            raise TypeError('reviewer must be IPerson: %s' % repr(reviewer))
        if old_status not in TeamMembershipStatus:
            raise TypeError("old_status must be TeamMembershipStatus: %s"
                            % repr(old_status))
        if new_status not in TeamMembershipStatus:
            raise TypeError("new_status must be TeamMembershipStatus: %s"
                            % repr(new_status))
        metadata = {
            'reviewer': reviewer.id,
            'old_status': old_status.name,
            'new_status': new_status.name,
            'last_change_comment': last_change_comment,
            }
        return super(MembershipNotificationJob, cls).create(
            minor_person=member, major_person=team, metadata=metadata)

    @property
    def member(self):
        return self.minor_person

    @property
    def team(self):
        return self.major_person

    @property
    def reviewer(self):
        return getUtility(IPersonSet).get(self.metadata['reviewer'])

    @property
    def old_status(self):
        return TeamMembershipStatus.items[self.metadata['old_status']]

    @property
    def new_status(self):
        return TeamMembershipStatus.items[self.metadata['new_status']]

    @property
    def last_change_comment(self):
        return self.metadata['last_change_comment']

    def run(self):
        """See `IMembershipNotificationJob`."""
        from lp.services.scripts import log
        from_addr = format_address(
            self.team.displayname, config.canonical.noreply_from_address)
        admin_emails = self.team.getTeamAdminsEmailAddresses()
        # person might be a self.team, so we can't rely on its preferredemail.
        self.member_email = get_contact_email_addresses(self.member)
        # Make sure we don't send the same notification twice to anybody.
        for email in self.member_email:
            if email in admin_emails:
                admin_emails.remove(email)

        if self.reviewer != self.member:
            self.reviewer_name = self.reviewer.unique_displayname
        else:
            self.reviewer_name = 'the user'

        if self.last_change_comment:
            comment = ("\n%s said:\n %s\n" % (
                self.reviewer.displayname, self.last_change_comment.strip()))
        else:
            comment = ""

        replacements = {
            'member_name': self.member.unique_displayname,
            'recipient_name': self.member.displayname,
            'team_name': self.team.unique_displayname,
            'team_url': canonical_url(self.team),
            'old_status': self.old_status.title,
            'new_status': self.new_status.title,
            'reviewer_name': self.reviewer_name,
            'comment': comment}

        template_name = 'membership-statuschange'
        subject = (
            'Membership change: %(member)s in %(team)s'
            % {
                'member': self.member.name,
                'team': self.team.name,
              })
        if self.new_status == TeamMembershipStatus.EXPIRED:
            template_name = 'membership-expired'
            subject = '%s expired from team' % self.member.name
        elif (self.new_status == TeamMembershipStatus.APPROVED and
            self.old_status != TeamMembershipStatus.ADMIN):
            if self.old_status == TeamMembershipStatus.INVITED:
                subject = ('Invitation to %s accepted by %s'
                        % (self.member.name, self.reviewer.name))
                template_name = 'membership-invitation-accepted'
            elif self.old_status == TeamMembershipStatus.PROPOSED:
                subject = '%s approved by %s' % (
                    self.member.name, self.reviewer.name)
            else:
                subject = '%s added by %s' % (
                    self.member.name, self.reviewer.name)
        elif self.new_status == TeamMembershipStatus.INVITATION_DECLINED:
            subject = ('Invitation to %s declined by %s'
                    % (self.member.name, self.reviewer.name))
            template_name = 'membership-invitation-declined'
        elif self.new_status == TeamMembershipStatus.DEACTIVATED:
            subject = '%s deactivated by %s' % (
                self.member.name, self.reviewer.name)
        elif self.new_status == TeamMembershipStatus.ADMIN:
            subject = '%s made admin by %s' % (
                self.member.name, self.reviewer.name)
        elif self.new_status == TeamMembershipStatus.DECLINED:
            subject = '%s declined by %s' % (
                self.member.name, self.reviewer.name)
        else:
            # Use the default template and subject.
            pass

        # Must have someone to mail, and be a non-open team (because open
        # teams are unrestricted, notifications on join/ leave do not help the
        # admins.
        if (len(admin_emails) != 0 and
            self.team.membership_policy != TeamMembershipPolicy.OPEN):
            admin_template = get_email_template(
                "%s-bulk.txt" % template_name, app='registry')
            for address in admin_emails:
                recipient = getUtility(IPersonSet).getByEmail(address)
                replacements['recipient_name'] = recipient.displayname
                msg = MailWrapper().format(
                    admin_template % replacements, force_wrap=True)
                simple_sendmail(from_addr, address, subject, msg)

        # The self.member can be a self.self.team without any
        # self.members, and in this case we won't have a single email
        # address to send this notification to.
        if self.member_email and self.reviewer != self.member:
            if self.member.is_team:
                template = '%s-bulk.txt' % template_name
            else:
                template = '%s-personal.txt' % template_name
            self.member_template = get_email_template(
                template, app='registry')
            for address in self.member_email:
                recipient = getUtility(IPersonSet).getByEmail(address)
                replacements['recipient_name'] = recipient.displayname
                msg = MailWrapper().format(
                    self.member_template % replacements, force_wrap=True)
                simple_sendmail(from_addr, address, subject, msg)
        log.debug('MembershipNotificationJob sent email')

    def __repr__(self):
        return (
            "<{self.__class__.__name__} about "
            "~{self.minor_person.name} in ~{self.major_person.name}; "
            "status={self.job.status}>").format(self=self)


class PersonMergeJob(PersonTransferJobDerived):
    """A Job that merges one person or team into another."""

    implements(IPersonMergeJob)
    classProvides(IPersonMergeJobSource)

    class_job_type = PersonTransferJobType.MERGE

    config = config.IPersonMergeJobSource

    @classmethod
    def create(cls, from_person, to_person, requester, reviewer=None,
               delete=False):
        """See `IPersonMergeJobSource`."""
        if (from_person.isMergePending() or
            (not delete and to_person.isMergePending())):
            return None
        if from_person.is_team:
            metadata = {'reviewer': reviewer.id}
        else:
            metadata = {}
        metadata['delete'] = bool(delete)
        if metadata['delete']:
            # Ideally not needed, but the DB column is not-null at the moment
            # and this minor bit of friction isn't worth changing that over.
            to_person = getUtility(ILaunchpadCelebrities).registry_experts
        return super(PersonMergeJob, cls).create(
            minor_person=from_person, major_person=to_person,
            metadata=metadata, requester=requester)

    @classmethod
    def find(cls, from_person=None, to_person=None, any_person=False):
        """See `IPersonMergeJobSource`."""
        conditions = [
            PersonTransferJob.job_type == cls.class_job_type,
            PersonTransferJob.job_id == Job.id,
            Job._status.is_in(Job.PENDING_STATUSES)]
        arg_conditions = []
        if from_person is not None:
            arg_conditions.append(
                PersonTransferJob.minor_person == from_person)
        if to_person is not None:
            arg_conditions.append(
                PersonTransferJob.major_person == to_person)
        if any_person and from_person is not None and to_person is not None:
            arg_conditions = [Or(*arg_conditions)]
        conditions.extend(arg_conditions)
        return DecoratedResultSet(
            IStore(PersonTransferJob).find(
                PersonTransferJob, *conditions), cls)

    @property
    def from_person(self):
        """See `IPersonMergeJob`."""
        return self.minor_person

    @property
    def to_person(self):
        """See `IPersonMergeJob`."""
        return self.major_person

    @property
    def reviewer(self):
        if 'reviewer' in self.metadata:
            return getUtility(IPersonSet).get(self.metadata['reviewer'])
        else:
            return None

    @property
    def log_name(self):
        return self.__class__.__name__

    def getErrorRecipients(self):
        """See `IPersonMergeJob`."""
        return [format_address_for_person(self.requester)]

    def run(self):
        """Perform the merge."""
        from_person_name = self.from_person.name
        to_person_name = self.to_person.name

        from lp.services.scripts import log
        if self.metadata.get('delete', False):
            log.debug(
                "%s is about to delete ~%s", self.log_name,
                from_person_name)
            merge_people(
                from_person=self.from_person,
                to_person=getUtility(ILaunchpadCelebrities).registry_experts,
                reviewer=self.reviewer, delete=True)
            log.debug(
                "%s has deleted ~%s", self.log_name,
                from_person_name)
        else:
            log.debug(
                "%s is about to merge ~%s into ~%s", self.log_name,
                from_person_name, to_person_name)
            merge_people(
                from_person=self.from_person, to_person=self.to_person,
                reviewer=self.reviewer)
            log.debug(
                "%s has merged ~%s into ~%s", self.log_name,
                from_person_name, to_person_name)

    def __repr__(self):
        return (
            "<{self.__class__.__name__} to merge "
            "~{self.from_person.name} into ~{self.to_person.name}; "
            "status={self.job.status}>").format(self=self)

    def getOperationDescription(self):
        return ('merging ~%s into ~%s' %
                (self.from_person.name, self.to_person.name))


class PersonDeactivateJob(PersonTransferJobDerived):
    """A Job that deactivates a person."""

    implements(IPersonDeactivateJob)
    classProvides(IPersonDeactivateJobSource)

    class_job_type = PersonTransferJobType.DEACTIVATE

    config = config.IPersonMergeJobSource

    @classmethod
    def create(cls, person):
        """See `IPersonMergeJobSource`."""
        # Minor person has to be not null, so use the janitor.
        janitor = getUtility(ILaunchpadCelebrities).janitor
        return super(PersonDeactivateJob, cls).create(
            minor_person=janitor, major_person=person, metadata={})

    @classmethod
    def find(cls, person=None):
        """See `IPersonMergeJobSource`."""
        conditions = [
            PersonTransferJob.job_type == cls.class_job_type,
            PersonTransferJob.job_id == Job.id,
            Job._status.is_in(Job.PENDING_STATUSES)]
        arg_conditions = []
        if person:
            arg_conditions.append(PersonTransferJob.major_person == person)
        conditions.extend(arg_conditions)
        return DecoratedResultSet(
            IStore(PersonTransferJob).find(
                PersonTransferJob, *conditions), cls)

    @property
    def person(self):
        """See `IPersonMergeJob`."""
        return self.major_person

    @property
    def log_name(self):
        return self.__class__.__name__

    def getErrorRecipients(self):
        """See `IPersonMergeJob`."""
        return [format_address_for_person(self.person)]

    def run(self):
        """Perform the merge."""
        from lp.services.scripts import log
        person_name = self.person.name
        log.debug('about to deactivate ~%s', person_name)
        self.person.deactivate(validate=False, pre_deactivate=False)
        log.debug('done deactivating ~%s', person_name)

    def __repr__(self):
        return (
            "<{self.__class__.__name__} to deactivate "
            "~{self.person.name}").format(self=self)

    def getOperationDescription(self):
        return 'deactivating ~%s' % self.person.name
