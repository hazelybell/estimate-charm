# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Classes that implement IBugTask and its related interfaces."""

__metaclass__ = type

__all__ = [
    'BugTaskDelta',
    'BugTaskToBugAdapter',
    'BugTask',
    'BugTaskSet',
    'bugtask_sort_key',
    'bug_target_from_key',
    'bug_target_to_key',
    'validate_new_target',
    'validate_target',
    ]


from collections import defaultdict
import datetime
from itertools import (
    chain,
    repeat,
    )
from operator import (
    attrgetter,
    itemgetter,
    )
import re

from lazr.lifecycle.event import (
    ObjectDeletedEvent,
    ObjectModifiedEvent,
    )
from lazr.lifecycle.snapshot import Snapshot
import pytz
from sqlobject import (
    ForeignKey,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import (
    And,
    Cast,
    Count,
    Exists,
    Join,
    LeftJoin,
    Not,
    Or,
    Select,
    SQL,
    Sum,
    )
from storm.info import ClassAlias
from storm.store import (
    EmptyResultSet,
    Store,
    )
from zope.component import getUtility
from zope.event import notify
from zope.interface import (
    implements,
    providedBy,
    )
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import (
    PROPRIETARY_INFORMATION_TYPES,
    PUBLIC_INFORMATION_TYPES,
    )
from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.interfaces.bug import IBugSet
from lp.bugs.interfaces.bugtarget import IBugTarget
from lp.bugs.interfaces.bugtask import (
    BUG_SUPERVISOR_BUGTASK_STATUSES,
    BugTaskImportance,
    BugTaskStatus,
    BugTaskStatusSearch,
    CannotDeleteBugtask,
    DB_INCOMPLETE_BUGTASK_STATUSES,
    DB_UNRESOLVED_BUGTASK_STATUSES,
    get_bugtask_status,
    IBugTask,
    IBugTaskDelta,
    IBugTaskSet,
    IllegalTarget,
    normalize_bugtask_status,
    RESOLVED_BUGTASK_STATUSES,
    UserCannotEditBugTaskAssignee,
    UserCannotEditBugTaskImportance,
    UserCannotEditBugTaskMilestone,
    UserCannotEditBugTaskStatus,
    )
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.registry.interfaces.distribution import (
    IDistribution,
    IDistributionSet,
    )
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.milestone import IMilestoneSet
from lp.registry.interfaces.milestonetag import IProjectGroupMilestoneTag
from lp.registry.interfaces.person import (
    validate_person,
    validate_public_person,
    )
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.registry.interfaces.role import IPersonRoles
from lp.registry.interfaces.sharingjob import (
    IRemoveArtifactSubscriptionsJobSource,
    )
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.registry.interfaces.sourcepackagename import ISourcePackageNameSet
from lp.registry.model.pillar import pillar_sort_key
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services import features
from lp.services.database.bulk import (
    create,
    load,
    load_related,
    )
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.nl_search import nl_phrase_search
from lp.services.database.sqlbase import (
    block_implicit_flushes,
    cursor,
    quote,
    SQLBase,
    sqlvalues,
    )
from lp.services.helpers import shortlist
from lp.services.propertycache import get_property_cache
from lp.services.searchbuilder import any
from lp.services.webapp.interfaces import ILaunchBag


def bugtask_sort_key(bugtask):
    """A sort key for a set of bugtasks. We want:

          - products first, followed by their productseries tasks
          - distro tasks, followed by their distroseries tasks
          - ubuntu first among the distros
    """
    product_name = None
    productseries_name = None
    distribution_name = None
    distroseries_name = None
    sourcepackage_name = None

    if bugtask.product:
        product_name = bugtask.product.name
    elif bugtask.productseries:
        productseries_name = bugtask.productseries.name
        product_name = bugtask.productseries.product.name

    if bugtask.distribution:
        distribution_name = bugtask.distribution.name

    if bugtask.distroseries:
        distroseries_name = bugtask.distroseries.version
        distribution_name = bugtask.distroseries.distribution.name

    if bugtask.sourcepackagename:
        sourcepackage_name = bugtask.sourcepackagename.name

    # Move ubuntu to the top.
    if distribution_name == 'ubuntu':
        distribution_name = '-'

    return (
        bugtask.bug.id, distribution_name, product_name, productseries_name,
        distroseries_name, sourcepackage_name)


def bug_target_from_key(product, productseries, distribution, distroseries,
                        sourcepackagename):
    """Returns the IBugTarget defined by the given DB column values."""
    if product:
        return product
    elif productseries:
        return productseries
    elif distribution:
        if sourcepackagename:
            return distribution.getSourcePackage(
                sourcepackagename)
        else:
            return distribution
    elif distroseries:
        if sourcepackagename:
            return distroseries.getSourcePackage(
                sourcepackagename)
        else:
            return distroseries
    else:
        raise AssertionError("Unable to determine bugtask target.")


def bug_target_to_key(target):
    """Returns the DB column values for an IBugTarget."""
    values = dict(
                product=None,
                productseries=None,
                distribution=None,
                distroseries=None,
                sourcepackagename=None,
                )
    if IProduct.providedBy(target):
        values['product'] = target
    elif IProductSeries.providedBy(target):
        values['productseries'] = target
    elif IDistribution.providedBy(target):
        values['distribution'] = target
    elif IDistroSeries.providedBy(target):
        values['distroseries'] = target
    elif IDistributionSourcePackage.providedBy(target):
        values['distribution'] = target.distribution
        values['sourcepackagename'] = target.sourcepackagename
    elif ISourcePackage.providedBy(target):
        values['distroseries'] = target.distroseries
        values['sourcepackagename'] = target.sourcepackagename
    else:
        raise AssertionError("Not an IBugTarget.")
    return values


class BugTaskDelta:
    """See `IBugTaskDelta`."""

    implements(IBugTaskDelta)

    def __init__(self, bugtask, status=None, importance=None,
                 assignee=None, milestone=None, bugwatch=None, target=None):
        self.bugtask = bugtask

        self.assignee = assignee
        self.bugwatch = bugwatch
        self.importance = importance
        self.milestone = milestone
        self.status = status
        self.target = target


def BugTaskToBugAdapter(bugtask):
    """Adapt an IBugTask to an IBug."""
    return bugtask.bug


class PassthroughValue:
    """A wrapper to allow setting values on conjoined bug tasks."""

    def __init__(self, value):
        self.value = value


@block_implicit_flushes
def validate_conjoined_attribute(self, attr, value):
    # If the value has been wrapped in a _PassthroughValue instance,
    # then we are being updated by our conjoined master: pass the
    # value through without any checking.
    if isinstance(value, PassthroughValue):
        return value.value

    # Check to see if the object is being instantiated.  This test is specific
    # to SQLBase.  Checking for specific attributes (like self.bug) is
    # insufficient and fragile.
    if self._SO_creating:
        return value

    # If this is a conjoined slave then call setattr on the master.
    # Effectively this means that making a change to the slave will
    # actually make the change to the master (which will then be passed
    # down to the slave, of course). This helps to prevent OOPSes when
    # people try to update the conjoined slave via the API.
    conjoined_master = self.conjoined_master
    if conjoined_master is not None:
        setattr(conjoined_master, attr, value)
        return value

    # If there is a conjoined slave, update that.
    conjoined_bugtask = self.conjoined_slave
    if conjoined_bugtask:
        setattr(conjoined_bugtask, attr, PassthroughValue(value))

    return value


def validate_status(self, attr, value):
    if value not in self._NON_CONJOINED_STATUSES:
        return validate_conjoined_attribute(self, attr, value)
    else:
        return value


def validate_assignee(self, attr, value):
    value = validate_conjoined_attribute(self, attr, value)
    # Check if this person is valid and not None.
    return validate_person(self, attr, value)


def validate_target(bug, target, retarget_existing=True,
                    check_source_package=True):
    """Validate a bugtask target against a bug's existing tasks.

    Checks that no conflicting tasks already exist.

    If the target is a source package, we need to check that it has been
    published in the distribution since we don't trust the vocabulary to
    enforce this. However, when using the UI, this check is done during the
    validation stage of form submission and we don't want to do it again since
    it uses an expensive query. So 'check_source_package' can be set to False.
    """
    if bug.getBugTask(target):
        raise IllegalTarget(
            "A fix for this bug has already been requested for %s"
            % target.displayname)

    if (IDistributionSourcePackage.providedBy(target) or
        ISourcePackage.providedBy(target)):
        # If the distribution has at least one series, check that the
        # source package has been published in the distribution.
        if (check_source_package and target.sourcepackagename is not None and
            len(target.distribution.series) > 0):
            try:
                target.distribution.guessPublishedSourcePackageName(
                    target.sourcepackagename.name)
            except NotFoundError as e:
                raise IllegalTarget(e[0])

    legal_types = target.pillar.getAllowedBugInformationTypes()
    new_pillar = target.pillar not in bug.affected_pillars
    if new_pillar and bug.information_type not in legal_types:
        raise IllegalTarget(
            "%s doesn't allow %s bugs." % (
            target.pillar.bugtargetdisplayname, bug.information_type.title))

    if bug.information_type in PROPRIETARY_INFORMATION_TYPES:
        # Perhaps we are replacing the one and only existing bugtask, in
        # which case that's ok.
        if retarget_existing and len(bug.bugtasks) <= 1:
            return
        # We can add a target so long as the pillar exists already.
        if (len(bug.affected_pillars) > 0
                and target.pillar not in bug.affected_pillars):
            raise IllegalTarget(
                "This proprietary bug already affects %s. "
                "Proprietary bugs cannot affect multiple projects."
                    % bug.default_bugtask.target.pillar.bugtargetdisplayname)


def validate_new_target(bug, target, check_source_package=True):
    """Validate a bugtask target to be added.

    Make sure that the isn't already a distribution task without a
    source package, or that such task is added only when the bug doesn't
    already have any tasks for the distribution.

    The same checks as `validate_target` does are also done.
    """
    if IDistribution.providedBy(target):
        # Prevent having a task on only the distribution if there's at
        # least one task already on the distribution, whether or not
        # that task also has a source package.
        distribution_tasks_for_bug = [
            bugtask for bugtask
            in shortlist(bug.bugtasks, longest_expected=50)
            if bugtask.distribution == target]

        if len(distribution_tasks_for_bug) > 0:
            raise IllegalTarget(
                "This bug is already on %s. Please specify an "
                "affected package in which the bug has not yet "
                "been reported." % target.displayname)
    elif IDistributionSourcePackage.providedBy(target):
        # Ensure that there isn't already a generic task open on the
        # distribution for this bug, because if there were, that task
        # should be reassigned to the sourcepackage, rather than a new
        # task opened.
        if bug.getBugTask(target.distribution) is not None:
            raise IllegalTarget(
                "This bug is already open on %s with no package "
                "specified. You should fill in a package name for "
                "the existing bug." % target.distribution.displayname)

    validate_target(
        bug, target, retarget_existing=False,
        check_source_package=check_source_package)


class BugTask(SQLBase):
    """See `IBugTask`."""
    implements(IBugTask)
    _table = "BugTask"
    _defaultOrder = ['distribution', 'product', 'productseries',
                     'distroseries', 'milestone', 'sourcepackagename']
    _CONJOINED_ATTRIBUTES = (
        "_status", "importance", "assigneeID", "milestoneID",
        "date_assigned", "date_confirmed", "date_inprogress",
        "date_closed", "date_incomplete", "date_left_new",
        "date_triaged", "date_fix_committed", "date_fix_released",
        "date_left_closed")
    _NON_CONJOINED_STATUSES = (BugTaskStatus.WONTFIX, )

    _inhibit_target_check = False

    bug = ForeignKey(dbName='bug', foreignKey='Bug', notNull=True)
    product = ForeignKey(
        dbName='product', foreignKey='Product',
        notNull=False, default=None)
    productseries = ForeignKey(
        dbName='productseries', foreignKey='ProductSeries',
        notNull=False, default=None)
    sourcepackagename = ForeignKey(
        dbName='sourcepackagename', foreignKey='SourcePackageName',
        notNull=False, default=None)
    distribution = ForeignKey(
        dbName='distribution', foreignKey='Distribution',
        notNull=False, default=None)
    distroseries = ForeignKey(
        dbName='distroseries', foreignKey='DistroSeries',
        notNull=False, default=None)
    milestone = ForeignKey(
        dbName='milestone', foreignKey='Milestone',
        notNull=False, default=None,
        storm_validator=validate_conjoined_attribute)
    _status = EnumCol(
        dbName='status', notNull=True,
        schema=(BugTaskStatus, BugTaskStatusSearch),
        default=BugTaskStatus.NEW,
        storm_validator=validate_status)
    importance = EnumCol(
        dbName='importance', notNull=True,
        schema=BugTaskImportance,
        default=BugTaskImportance.UNDECIDED,
        storm_validator=validate_conjoined_attribute)
    assignee = ForeignKey(
        dbName='assignee', foreignKey='Person',
        storm_validator=validate_assignee,
        notNull=False, default=None)
    bugwatch = ForeignKey(dbName='bugwatch', foreignKey='BugWatch',
        notNull=False, default=None)
    date_assigned = UtcDateTimeCol(notNull=False, default=None,
        storm_validator=validate_conjoined_attribute)
    datecreated = UtcDateTimeCol(notNull=False, default=UTC_NOW)
    date_confirmed = UtcDateTimeCol(notNull=False, default=None,
        storm_validator=validate_conjoined_attribute)
    date_inprogress = UtcDateTimeCol(notNull=False, default=None,
        storm_validator=validate_conjoined_attribute)
    date_closed = UtcDateTimeCol(notNull=False, default=None,
        storm_validator=validate_conjoined_attribute)
    date_incomplete = UtcDateTimeCol(notNull=False, default=None,
        storm_validator=validate_conjoined_attribute)
    date_left_new = UtcDateTimeCol(notNull=False, default=None,
        storm_validator=validate_conjoined_attribute)
    date_triaged = UtcDateTimeCol(notNull=False, default=None,
        storm_validator=validate_conjoined_attribute)
    date_fix_committed = UtcDateTimeCol(notNull=False, default=None,
        storm_validator=validate_conjoined_attribute)
    date_fix_released = UtcDateTimeCol(notNull=False, default=None,
        storm_validator=validate_conjoined_attribute)
    date_left_closed = UtcDateTimeCol(notNull=False, default=None,
        storm_validator=validate_conjoined_attribute)
    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    # The targetnamecache is a value that is only supposed to be set
    # when a bugtask is created/modified or by the
    # update-bugtask-targetnamecaches cronscript. For this reason it's
    # not exposed in the interface, and client code should always use
    # the bugtargetname and bugtargetdisplayname properties.
    #
    # This field is actually incorrectly named, since it currently
    # stores the bugtargetdisplayname.
    targetnamecache = StringCol(
        dbName='targetnamecache', notNull=False, default=None)

    @property
    def status(self):
        if self._status in DB_INCOMPLETE_BUGTASK_STATUSES:
            return BugTaskStatus.INCOMPLETE
        return self._status

    @property
    def title(self):
        """See `IBugTask`."""
        return 'Bug #%s in %s: "%s"' % (
            self.bug.id, self.bugtargetdisplayname, self.bug.title)

    @property
    def bug_subscribers(self):
        """See `IBugTask`."""
        return tuple(
            chain(self.bug.getDirectSubscribers(),
                  self.bug.getIndirectSubscribers()))

    @property
    def bugtargetname(self):
        """See `IBugTask`."""
        return self.target.bugtargetname

    @property
    def target(self):
        """See `IBugTask`."""
        return bug_target_from_key(
            self.product, self.productseries, self.distribution,
            self.distroseries, self.sourcepackagename)

    @property
    def related_tasks(self):
        """See `IBugTask`."""
        other_tasks = [
            task for task in self.bug.bugtasks if task != self]

        return other_tasks

    @property
    def pillar(self):
        """See `IBugTask`."""
        return self.target.pillar

    @property
    def other_affected_pillars(self):
        """See `IBugTask`."""
        result = set()
        this_pillar = self.pillar
        for task in self.bug.bugtasks:
            that_pillar = task.pillar
            if that_pillar != this_pillar:
                result.add(that_pillar)
        return sorted(result, key=pillar_sort_key)

    @property
    def bugtargetdisplayname(self):
        """See `IBugTask`."""
        return self.targetnamecache

    @property
    def age(self):
        """See `IBugTask`."""
        now = datetime.datetime.now(pytz.UTC)

        return now - self.datecreated

    @property
    def task_age(self):
        """See `IBugTask`."""
        return self.age.seconds

    # Several other classes need to generate lists of bug tasks, and
    # one thing they often have to filter for is completeness. We maintain
    # this single canonical query string here so that it does not have to be
    # cargo culted into Product, Distribution, ProductSeries etc
    completeness_clause = """
        BugTask.status IN ( %s )
        """ % ','.join([str(a.value) for a in RESOLVED_BUGTASK_STATUSES])

    @property
    def is_complete(self):
        """See `IBugTask`.

        Note that this should be kept in sync with the completeness_clause
        above.
        """
        return self._status in RESOLVED_BUGTASK_STATUSES

    def canBeDeleted(self):
        try:
            self.checkCanBeDeleted()
        except Exception:
            return False
        return True

    def checkCanBeDeleted(self):
        # Bug.bugtasks is a cachedproperty, so this is pretty much free
        # to call. Better than a manual count query, at any rate.
        if len(self.bug.bugtasks) < 2:
            raise CannotDeleteBugtask(
                "Cannot delete only bugtask affecting: %s."
                % self.target.bugtargetdisplayname)

    def delete(self, who=None):
        """See `IBugTask`."""
        if who is None:
            who = getUtility(ILaunchBag).user

        # Raise an error if the bugtask cannot be deleted.
        self.checkCanBeDeleted()

        bug = self.bug
        target = self.target
        notify(ObjectDeletedEvent(self, who))
        self.destroySelf()
        del get_property_cache(bug).bugtasks
        self.bug._reconcileAccess()

        # When a task is deleted, we also delete it's BugNomination entry
        # if there is one. Sadly, getNominationFor() can return None or
        # raise NotFoundError so we need to check for both.
        try:
            nomination = bug.getNominationFor(target)
            if nomination is not None:
                nomination.destroySelf()
        except NotFoundError:
            # We don't care if there isn't a nomination
            pass

    def findSimilarBugs(self, user, limit=10):
        """See `IBugTask`."""
        if self.product is not None:
            context_params = {'product': self.product}
        elif (self.sourcepackagename is not None and
            self.distribution is not None):
            context_params = {
                'distribution': self.distribution,
                'sourcepackagename': self.sourcepackagename,
                }
        elif self.distribution is not None:
            context_params = {'distribution': self.distribution}
        else:
            raise AssertionError("BugTask doesn't have a searchable target.")

        matching_bugtasks = getUtility(IBugTaskSet).findSimilar(
            user, self.bug.title, **context_params)

        matching_bugs = getUtility(IBugSet).getDistinctBugsForBugTasks(
            matching_bugtasks, user, limit)

        # Make sure to exclude the bug of the current bugtask.
        return [bug for bug in matching_bugs if bug.id != self.bugID]

    def subscribe(self, person, subscribed_by):
        """See `IBugTask`."""
        return self.bug.subscribe(person, subscribed_by)

    def isSubscribed(self, person):
        """See `IBugTask`."""
        return self.bug.isSubscribed(person)

    def _syncSourcePackages(self, new_spn, user):
        """Synchronize changes to source packages with other distrotasks.

        If one distroseriestask's source package is changed, all the
        other distroseriestasks with the same distribution and source
        package has to be changed, as well as the corresponding
        distrotask.
        """
        if self.bug is None or not (self.distribution or self.distroseries):
            # The validator is being called on a new or non-distro task.
            return
        distribution = self.distribution or self.distroseries.distribution
        for bugtask in self.related_tasks:
            relevant = (
                bugtask.sourcepackagename == self.sourcepackagename and
                distribution in (
                    bugtask.distribution,
                    getattr(bugtask.distroseries, 'distribution', None)))
            if relevant:
                key = bug_target_to_key(bugtask.target)
                key['sourcepackagename'] = new_spn
                # The relevance check above and the fact that the distro series
                # task is already on the bug means we don't need to revalidate.
                bugtask.transitionToTarget(
                    bug_target_from_key(**key),
                    user, validate=False, _sync_sourcepackages=False)

    def getContributorInfo(self, user, person):
        """See `IBugTask`."""
        result = {}
        result['is_contributor'] = person.isBugContributorInTarget(
            user, self.pillar)
        result['person_name'] = person.displayname
        result['pillar_name'] = self.pillar.displayname
        return result

    def getConjoinedMaster(self, bugtasks, bugtasks_by_package=None):
        """See `IBugTask`."""
        conjoined_master = None
        if self.distribution:
            if bugtasks_by_package is None:
                bugtasks_by_package = (
                    self.bug.getBugTasksByPackageName(bugtasks))
            bugtasks = bugtasks_by_package[self.sourcepackagename]
            possible_masters = [
                bugtask for bugtask in bugtasks
                if (bugtask.distroseries is not None and
                    bugtask.sourcepackagename == self.sourcepackagename)]
            # Return early, so that we don't have to get currentseries,
            # which is expensive.
            if len(possible_masters) == 0:
                return None
            current_series = self.distribution.currentseries
            for bugtask in possible_masters:
                if bugtask.distroseries == current_series:
                    conjoined_master = bugtask
                    break
        elif self.product:
            assert self.product.development_focusID is not None, (
                'A product should always have a development series.')
            devel_focusID = self.product.development_focusID
            for bugtask in bugtasks:
                if bugtask.productseriesID == devel_focusID:
                    conjoined_master = bugtask
                    break

        if (conjoined_master is not None and
            conjoined_master.status in self._NON_CONJOINED_STATUSES):
            conjoined_master = None
        return conjoined_master

    def _get_shortlisted_bugtasks(self):
        return shortlist(self.bug.bugtasks, longest_expected=200)

    @property
    def conjoined_master(self):
        """See `IBugTask`."""
        return self.getConjoinedMaster(self._get_shortlisted_bugtasks())

    @property
    def conjoined_slave(self):
        """See `IBugTask`."""
        conjoined_slave = None
        if self.distroseries:
            distribution = self.distroseries.distribution
            if self.distroseries != distribution.currentseries:
                # Only current series tasks are conjoined.
                return None
            for bugtask in self._get_shortlisted_bugtasks():
                if (bugtask.distribution == distribution and
                    bugtask.sourcepackagename == self.sourcepackagename):
                    conjoined_slave = bugtask
                    break
        elif self.productseries:
            product = self.productseries.product
            if self.productseries != product.development_focus:
                # Only development focus tasks are conjoined.
                return None
            for bugtask in self._get_shortlisted_bugtasks():
                if bugtask.product == product:
                    conjoined_slave = bugtask
                    break

        if (conjoined_slave is not None and
            self.status in self._NON_CONJOINED_STATUSES):
            conjoined_slave = None
        return conjoined_slave

    def _syncFromConjoinedSlave(self):
        """Ensure the conjoined master is synched from its slave.

        This method should be used only directly after when the
        conjoined master has been created after the slave, to ensure
        that they are in sync from the beginning.
        """
        conjoined_slave = self.conjoined_slave

        for synched_attr in self._CONJOINED_ATTRIBUTES:
            slave_attr_value = getattr(conjoined_slave, synched_attr)
            # Bypass our checks that prevent setting attributes on
            # conjoined masters by calling the underlying sqlobject
            # setter methods directly.
            setattr(self, synched_attr, PassthroughValue(slave_attr_value))

    def transitionToMilestone(self, new_milestone, user):
        """See `IBugTask`."""
        if not self.userHasBugSupervisorPrivileges(user):
            raise UserCannotEditBugTaskMilestone(
                "User does not have sufficient permissions "
                "to edit the bug task milestone.")
        self.milestone = new_milestone
        # Clear the recipient caches so that the milestone subscribers are
        # notified.
        self.bug.clearBugNotificationRecipientsCache()

    def transitionToImportance(self, new_importance, user):
        """See `IBugTask`."""
        if not self.userHasBugSupervisorPrivileges(user):
            raise UserCannotEditBugTaskImportance(
                "User does not have sufficient permissions "
                "to edit the bug task importance.")
        else:
            self.importance = new_importance

    # START TEMPORARY BIT FOR BUGTASK AUTOCONFIRM FEATURE FLAG.
    _parse_launchpad_names = re.compile(r"[a-z0-9][a-z0-9\+\.\-]+").findall

    def _checkAutoconfirmFeatureFlag(self):
        """Does a feature flag enable automatic switching of our bugtasks?"""
        # This method should be ripped out if we determine that we like
        # this behavior for all projects.
        # This is a bit of a feature flag hack, but has been discussed as
        # a reasonable way to deploy this quickly.
        pillar = self.pillar
        if IDistribution.providedBy(pillar):
            flag_name = 'bugs.autoconfirm.enabled_distribution_names'
        else:
            assert IProduct.providedBy(pillar), 'unexpected pillar'
            flag_name = 'bugs.autoconfirm.enabled_product_names'
        enabled = features.getFeatureFlag(flag_name)
        if enabled is None:
            return False
        if (enabled.strip() != '*' and
            pillar.name not in self._parse_launchpad_names(enabled)):
            # We are not generically enabled ('*') and our pillar's name
            # is not explicitly enabled.
            return False
        return True
    # END TEMPORARY BIT FOR BUGTASK AUTOCONFIRM FEATURE FLAG.

    def maybeConfirm(self):
        """Maybe confirm this bugtask.
        Only call this if the bug._shouldConfirmBugtasks().
        This adds the further constraint that the bugtask needs to be NEW,
        and not imported from an external bug tracker.
        """
        if (self.status == BugTaskStatus.NEW
            and self.bugwatch is None
            # START TEMPORARY BIT FOR BUGTASK AUTOCONFIRM FEATURE FLAG.
            and self._checkAutoconfirmFeatureFlag()
            # END TEMPORARY BIT FOR BUGTASK AUTOCONFIRM FEATURE FLAG.
            ):
            janitor = getUtility(ILaunchpadCelebrities).janitor
            bugtask_before_modification = Snapshot(
                self, providing=providedBy(self))
            # Create a bug message explaining why the janitor auto-confirmed
            # the bugtask.
            msg = ("Status changed to 'Confirmed' because the bug "
                   "affects multiple users.")
            self.bug.newMessage(owner=janitor, content=msg)
            self.transitionToStatus(BugTaskStatus.CONFIRMED, janitor)
            notify(ObjectModifiedEvent(
                self, bugtask_before_modification, ['status'], user=janitor))

    def canTransitionToStatus(self, new_status, user):
        """See `IBugTask`."""
        new_status = normalize_bugtask_status(new_status)
        if (self.status == BugTaskStatus.FIXRELEASED and
           (user.id == self.bug.ownerID or user.inTeam(self.bug.owner))):
            return True
        elif self.userHasBugSupervisorPrivileges(user):
            return True
        else:
            return (self.status not in (
                        BugTaskStatus.WONTFIX, BugTaskStatus.FIXRELEASED)
                    and new_status not in BUG_SUPERVISOR_BUGTASK_STATUSES)

    def transitionToStatus(self, new_status, user, when=None):
        """See `IBugTask`."""
        if not new_status or user is None:
            # This is mainly to facilitate tests which, unlike the
            # normal status form, don't always submit a status when
            # testing the edit form.
            return

        new_status = normalize_bugtask_status(new_status)

        if not self.canTransitionToStatus(new_status, user):
            raise UserCannotEditBugTaskStatus(
                "Only Bug Supervisors may change status to %s." % (
                    new_status.title,))

        if new_status == BugTaskStatus.INCOMPLETE:
            # We store INCOMPLETE as INCOMPLETE_WITHOUT_RESPONSE so that it
            # can be queried on efficiently.
            if (when is None or self.bug.date_last_message is None or
                when > self.bug.date_last_message):
                new_status = BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE
            else:
                new_status = BugTaskStatusSearch.INCOMPLETE_WITH_RESPONSE

        if self._status == new_status:
            # No change in the status, so nothing to do.
            return

        old_status = self.status
        self._status = new_status

        if new_status == BugTaskStatus.UNKNOWN:
            # Ensure that all status-related dates are cleared,
            # because it doesn't make sense to have any values set for
            # date_confirmed, date_closed, etc. when the status
            # becomes UNKNOWN.
            self.date_confirmed = None
            self.date_inprogress = None
            self.date_closed = None
            self.date_incomplete = None
            self.date_triaged = None
            self.date_fix_committed = None
            self.date_fix_released = None

            return

        if when is None:
            when = datetime.datetime.now(pytz.UTC)

        # Record the date of the particular kinds of transitions into
        # certain states.
        if ((old_status < BugTaskStatus.CONFIRMED) and
            (new_status >= BugTaskStatus.CONFIRMED)):
            # Even if the bug task skips the Confirmed status
            # (e.g. goes directly to Fix Committed), we'll record a
            # confirmed date at the same time anyway, otherwise we get
            # a strange gap in our data, and potentially misleading
            # reports.
            self.date_confirmed = when

        if ((old_status < BugTaskStatus.INPROGRESS) and
            (new_status >= BugTaskStatus.INPROGRESS)):
            # Same idea with In Progress as the comment above about
            # Confirmed.
            self.date_inprogress = when

        if (old_status == BugTaskStatus.NEW and
            new_status > BugTaskStatus.NEW and
            self.date_left_new is None):
            # This task is leaving the NEW status for the first time
            self.date_left_new = when

        # If the new status is equal to or higher
        # than TRIAGED, we record a `date_triaged`
        # to mark the fact that the task has passed
        # through this status.
        if (old_status < BugTaskStatus.TRIAGED and
            new_status >= BugTaskStatus.TRIAGED):
            # This task is now marked as TRIAGED
            self.date_triaged = when

        # If the new status is equal to or higher
        # than FIXCOMMITTED, we record a `date_fixcommitted`
        # to mark the fact that the task has passed
        # through this status.
        if (old_status < BugTaskStatus.FIXCOMMITTED and
            new_status >= BugTaskStatus.FIXCOMMITTED):
            # This task is now marked as FIXCOMMITTED
            self.date_fix_committed = when

        # If the new status is equal to or higher
        # than FIXRELEASED, we record a `date_fixreleased`
        # to mark the fact that the task has passed
        # through this status.
        if (old_status < BugTaskStatus.FIXRELEASED and
            new_status >= BugTaskStatus.FIXRELEASED):
            # This task is now marked as FIXRELEASED
            self.date_fix_released = when

        # Bugs can jump in and out of 'incomplete' status
        # and for just as long as they're marked incomplete
        # we keep a date_incomplete recorded for them.
        if new_status in DB_INCOMPLETE_BUGTASK_STATUSES:
            self.date_incomplete = when
        else:
            self.date_incomplete = None

        if ((old_status in DB_UNRESOLVED_BUGTASK_STATUSES) and
            (new_status in RESOLVED_BUGTASK_STATUSES)):
            self.date_closed = when

        if ((old_status in RESOLVED_BUGTASK_STATUSES) and
            (new_status in DB_UNRESOLVED_BUGTASK_STATUSES)):
            self.date_left_closed = when

        # Ensure that we don't have dates recorded for state
        # transitions, if the bugtask has regressed to an earlier
        # workflow state. We want to ensure that, for example, a
        # bugtask that went New => Confirmed => New
        # has a dateconfirmed value of None.
        if new_status in DB_UNRESOLVED_BUGTASK_STATUSES:
            self.date_closed = None

        if new_status < BugTaskStatus.CONFIRMED:
            self.date_confirmed = None

        if new_status < BugTaskStatus.INPROGRESS:
            self.date_inprogress = None

        if new_status < BugTaskStatus.TRIAGED:
            self.date_triaged = None

        if new_status < BugTaskStatus.FIXCOMMITTED:
            self.date_fix_committed = None

        if new_status < BugTaskStatus.FIXRELEASED:
            self.date_fix_released = None

    def userCanSetAnyAssignee(self, user):
        """See `IBugTask`."""
        if user is None:
            return False
        elif self.pillar.bug_supervisor is None:
            return True
        else:
            return self.userHasBugSupervisorPrivileges(user)

    def userCanUnassign(self, user):
        """See `IBugTask`."""
        return user is not None

    def canTransitionToAssignee(self, assignee):
        """See `IBugTask`."""
        # All users can assign and unassign themselves and their teams,
        # but only project owners, bug supervisors, project/distribution
        # drivers and Launchpad admins can assign others.
        user = getUtility(ILaunchBag).user
        return (
            user is not None and (
                user.inTeam(assignee) or
                (assignee is None and self.userCanUnassign(user)) or
                self.userCanSetAnyAssignee(user)))

    def transitionToAssignee(self, assignee, validate=True):
        """See `IBugTask`."""
        if assignee == self.assignee:
            # No change to the assignee, so nothing to do.
            return

        if validate and not self.canTransitionToAssignee(assignee):
            raise UserCannotEditBugTaskAssignee(
                'Regular users can assign and unassign only themselves and '
                'their teams. Only project owners, bug supervisors, drivers '
                'and release managers can assign others.')

        if self.assignee and not assignee:
            # The assignee is being cleared, so clear the date_assigned
            # value.
            self.date_assigned = None
        if not self.assignee and assignee:
            # The task is going from not having an assignee to having
            # one, so record when this happened
            self.date_assigned = datetime.datetime.now(pytz.UTC)

        self.assignee = assignee

    def validateTransitionToTarget(self, target, check_source_package=True):
        """See `IBugTask`."""
        from lp.registry.model.distroseries import DistroSeries

        # Check if any series are involved. You can't retarget series
        # tasks. Except for DistroSeries/SourcePackage tasks, which can
        # only be retargetted to another SourcePackage in the same
        # DistroSeries, or the DistroSeries.
        interfaces = set(providedBy(target))
        interfaces.update(providedBy(self.target))
        if IProductSeries in interfaces:
            raise IllegalTarget(
                "Series tasks may only be created by approving nominations.")
        elif interfaces.intersection((IDistroSeries, ISourcePackage)):
            series = set()
            for potential_target in (target, self.target):
                if IDistroSeries.providedBy(potential_target):
                    series.add(potential_target)
                elif ISourcePackage.providedBy(potential_target):
                    series.add(potential_target.distroseries)
                else:
                    series = set()
                    break
            if len(series) != 1:
                raise IllegalTarget(
                    "Distribution series tasks may only be retargeted "
                    "to a package within the same series.")
        # Because of the mildly insane way that DistroSeries nominations
        # work (they affect all Distributions and
        # DistributionSourcePackages), we can't sensibly allow
        # pillar changes to/from distributions with series tasks on this
        # bug. That would require us to create or delete tasks.
        # Changing just the sourcepackagename is OK, though, as a
        # validator on sourcepackagename will change all related tasks.
        elif interfaces.intersection(
            (IDistribution, IDistributionSourcePackage)):
            # Work out the involved distros (will include None if there
            # are product tasks).
            distros = set()
            for potential_target in (target, self.target):
                if IDistribution.providedBy(potential_target.pillar):
                    distros.add(potential_target.pillar)
                else:
                    distros.add(None)
            if len(distros) > 1:
                # Multiple distros involved. Check that none of their
                # series have tasks on this bug.
                if not Store.of(self).find(
                    BugTask,
                    BugTask.bugID == self.bugID,
                    BugTask.distroseriesID == DistroSeries.id,
                    DistroSeries.distributionID.is_in(
                        distro.id for distro in distros if distro),
                    ).is_empty():
                    raise IllegalTarget(
                        "Distribution tasks with corresponding series "
                        "tasks may only be retargeted to a different "
                        "package.")

        validate_target(
            self.bug, target, check_source_package=check_source_package)

    def transitionToTarget(self, target, user, validate=True,
                           _sync_sourcepackages=True):
        """See `IBugTask`.

        If validate is True then we need to check that the new target is valid,
        otherwise the check has already been done (eg during form submission)
        and we don't need to repeat it.

        If _sync_sourcepackages is True (the default) and the
        sourcepackagename is being changed, any other tasks for the same
        name in this distribution will have their names updated to
        match. This should only be used by _syncSourcePackages.
        """
        if self.target == target:
            return

        if validate:
            self.validateTransitionToTarget(target)

        target_before_change = self.target

        if (self.milestone is not None and
            self.milestone.target != target.pillar):
            # If the milestone for this bugtask is set, we
            # have to make sure that it's a milestone of the
            # current target, or reset it to None
            self.milestone = None

        new_key = bug_target_to_key(target)

        # As a special case, if the sourcepackagename has changed then
        # we update any other tasks for the same distribution and
        # sourcepackagename. This keeps series tasks consistent.
        if (_sync_sourcepackages and
            new_key['sourcepackagename'] != self.sourcepackagename):
            self._syncSourcePackages(new_key['sourcepackagename'], user)

        for name, value in new_key.iteritems():
            setattr(self, name, value)
        self.updateTargetNameCache()
        self.bug._reconcileAccess()

        # START TEMPORARY BIT FOR BUGTASK AUTOCONFIRM FEATURE FLAG.
        # We also should see if we ought to auto-transition to the
        # CONFIRMED status.
        if (self.target != target_before_change and
            self.bug.shouldConfirmBugtasks()):
            self.maybeConfirm()
        # END TEMPORARY BIT FOR BUGTASK AUTOCONFIRM FEATURE FLAG.

        # As a result of the transition, some subscribers may no longer
        # have access to the parent bug. We need to run a job to remove any
        # such subscriptions.
        self.bug.clearBugNotificationRecipientsCache()
        getUtility(IRemoveArtifactSubscriptionsJobSource).create(
            user, [self.bug], pillar=target_before_change.pillar)

    def updateTargetNameCache(self, newtarget=None):
        """See `IBugTask`."""
        if newtarget is None:
            newtarget = self.target
        targetname = newtarget.bugtargetdisplayname
        if self.targetnamecache != targetname:
            self.targetnamecache = targetname

    def getPackageComponent(self):
        """See `IBugTask`."""
        if ISourcePackage.providedBy(self.target):
            return self.target.latest_published_component
        if IDistributionSourcePackage.providedBy(self.target):
            spph = self.target.latest_overall_publication
            if spph:
                return spph.component
        return None

    def asEmailHeaderValue(self):
        """See `IBugTask`."""
        # Calculate an appropriate display value for the assignee.
        if self.assignee:
            if self.assignee.preferredemail:
                assignee_value = self.assignee.preferredemail.email
            else:
                # There is an assignee with no preferredemail, so we'll
                # "degrade" to the assignee.name. This might happen for teams
                # that don't have associated emails or when a bugtask was
                # imported from an external source and had its assignee set
                # automatically, even though the assignee may not even know
                # they have an account in Launchpad. :)
                assignee_value = self.assignee.name
        else:
            assignee_value = 'None'

        # Calculate an appropriate display value for the sourcepackage.
        if self.sourcepackagename:
            sourcepackagename_value = self.sourcepackagename.name
        else:
            # There appears to be no sourcepackagename associated with this
            # task.
            sourcepackagename_value = 'None'

        # Calculate an appropriate display value for the component, if the
        # target looks like some kind of source package.
        component = self.getPackageComponent()
        if component is None:
            component_name = 'None'
        else:
            component_name = component.name

        if self.product:
            header_value = 'product=%s;' % self.target.name
        elif self.productseries:
            header_value = 'product=%s; productseries=%s;' % (
                self.productseries.product.name, self.productseries.name)
        elif self.distribution:
            header_value = ((
                'distribution=%(distroname)s; '
                'sourcepackage=%(sourcepackagename)s; '
                'component=%(componentname)s;') %
                {'distroname': self.distribution.name,
                 'sourcepackagename': sourcepackagename_value,
                 'componentname': component_name})
        elif self.distroseries:
            header_value = ((
                'distribution=%(distroname)s; '
                'distroseries=%(distroseriesname)s; '
                'sourcepackage=%(sourcepackagename)s; '
                'component=%(componentname)s;') %
                {'distroname': self.distroseries.distribution.name,
                 'distroseriesname': self.distroseries.name,
                 'sourcepackagename': sourcepackagename_value,
                 'componentname': component_name})
        else:
            raise AssertionError('Unknown BugTask context: %r.' % self)

        # We only want to have a milestone field in the header if there's
        # a milestone set for the bug.
        if self.milestone:
            header_value += ' milestone=%s;' % self.milestone.name

        header_value += ((
            ' status=%(status)s; importance=%(importance)s; '
            'assignee=%(assignee)s;') %
            {'status': self.status.title,
             'importance': self.importance.title,
             'assignee': assignee_value})

        return header_value

    def getDelta(self, old_task):
        """See `IBugTask`."""
        # calculate the differences in the fields that both types of tasks
        # have in common
        changes = {}
        for field_name in ("target", "status", "importance",
                           "assignee", "bugwatch", "milestone"):
            old_val = getattr(old_task, field_name)
            new_val = getattr(self, field_name)
            if old_val != new_val:
                changes[field_name] = {}
                changes[field_name]["old"] = old_val
                changes[field_name]["new"] = new_val

        if changes:
            changes["bugtask"] = self
            return BugTaskDelta(**changes)
        else:
            return None

    @classmethod
    def userHasDriverPrivilegesContext(cls, context, user):
        """Does the user have driver privileges for the given context?

        :return: a boolean.
        """
        if not user:
            return False
        role = IPersonRoles(user)
        # Admins can always change bug details.
        if role.in_admin:
            return True

        # Similar to admins, the Bug Watch Updater, Bug Importer and
        # Janitor can always change bug details.
        if (
            role.in_bug_watch_updater or role.in_bug_importer or
            role.in_janitor):
            return True

        # If you're the owner or a driver, you can change bug details.
        owner_context = context
        if IBugTarget.providedBy(context):
            owner_context = context.pillar
        return (
            role.isOwner(owner_context) or role.isOneOfDrivers(context))

    @classmethod
    def userHasBugSupervisorPrivilegesContext(cls, context, user):
        """Does the user have bug supervisor privileges for the given
        context?

        :return: a boolean.
        """
        if not user:
            return False
        role = IPersonRoles(user)
        # If you have driver privileges, or are the bug supervisor, you can
        # change bug details.
        supervisor_context = context
        if IBugTarget.providedBy(context):
            supervisor_context = context.pillar
        return (
            cls.userHasDriverPrivilegesContext(context, user) or
            role.isBugSupervisor(supervisor_context))

    def userHasDriverPrivileges(self, user):
        """See `IBugTask`."""
        return self.userHasDriverPrivilegesContext(self.target, user)

    def userHasBugSupervisorPrivileges(self, user):
        """See `IBugTask`."""
        return self.userHasBugSupervisorPrivilegesContext(self.target, user)

    def __repr__(self):
        return "<BugTask for bug %s on %r>" % (self.bugID, self.target)


class BugTaskSet:
    """See `IBugTaskSet`."""
    implements(IBugTaskSet)

    title = "A set of bug tasks"

    @property
    def open_bugtask_search(self):
        """See `IBugTaskSet`."""
        return BugTaskSearchParams(
            user=getUtility(ILaunchBag).user,
            status=any(*DB_UNRESOLVED_BUGTASK_STATUSES),
            omit_dupes=True)

    def get(self, task_id):
        """See `IBugTaskSet`."""
        # XXX: JSK: 2007-12-19: This method should probably return
        # None when task_id is not present. See:
        # https://bugs.launchpad.net/launchpad/+bug/123592
        try:
            bugtask = BugTask.get(task_id)
        except SQLObjectNotFound:
            raise NotFoundError("BugTask with ID %s does not exist." %
                                str(task_id))
        return bugtask

    def getBugTaskTags(self, bugtasks):
        """See `IBugTaskSet`"""
        # Import locally to avoid circular imports.
        from lp.bugs.model.bug import Bug, BugTag
        bugtask_ids = set(bugtask.id for bugtask in bugtasks)
        bug_ids = set(bugtask.bugID for bugtask in bugtasks)
        tags = IStore(BugTag).find(
            (BugTag.tag, BugTask.id),
            BugTask.bug == Bug.id,
            BugTag.bug == Bug.id,
            BugTag.bugID.is_in(bug_ids),
            BugTask.id.is_in(bugtask_ids)).order_by(BugTag.tag)
        tags_by_bugtask = defaultdict(list)
        for tag_name, bugtask_id in tags:
            tags_by_bugtask[bugtask_id].append(tag_name)
        return dict(tags_by_bugtask)

    def getBugTaskPeople(self, bugtasks):
        """See `IBugTaskSet`"""
        # Avoid circular imports.
        from lp.registry.interfaces.person import IPersonSet
        people_ids = set(
            [bugtask.assigneeID for bugtask in bugtasks] +
            [bugtask.bug.ownerID for bugtask in bugtasks])
        people = getUtility(IPersonSet).getPrecachedPersonsFromIDs(people_ids)
        return dict(
            (person.id, person) for person in people)

    def getBugTaskBadgeProperties(self, bugtasks):
        """See `IBugTaskSet`."""
        # Import locally to avoid circular imports.
        from lp.blueprints.model.specificationbug import SpecificationBug
        from lp.bugs.model.bug import Bug
        from lp.bugs.model.bugbranch import BugBranch

        bug_ids = set(bugtask.bugID for bugtask in bugtasks)
        bug_ids_with_specifications = set(IStore(SpecificationBug).find(
            SpecificationBug.bugID,
            SpecificationBug.bugID.is_in(bug_ids)))
        bug_ids_with_branches = set(IStore(BugBranch).find(
                BugBranch.bugID, BugBranch.bugID.is_in(bug_ids)))
        # Badging looks up milestones too : eager load into the storm cache.
        milestoneset = getUtility(IMilestoneSet)
        # And trigger a load:
        milestone_ids = set(map(attrgetter('milestoneID'), bugtasks))
        milestone_ids.discard(None)
        if milestone_ids:
            list(milestoneset.getByIds(milestone_ids))

        # Check if the bugs are cached. If not, cache all uncached bugs
        # at once to avoid one query per bugtask. We could rely on the
        # Storm cache, but this is explicit.
        bugs = dict(
            (bug.id, bug)
            for bug in IStore(Bug).find(Bug, Bug.id.is_in(bug_ids)).cached())
        uncached_ids = bug_ids.difference(bug_id for bug_id in bugs)
        if len(uncached_ids) > 0:
            bugs.update(dict(IStore(Bug).find((Bug.id, Bug),
                                              Bug.id.is_in(uncached_ids))))

        badge_properties = {}
        for bugtask in bugtasks:
            bug = bugs[bugtask.bugID]
            badge_properties[bugtask] = {
                'has_specification':
                    bug.id in bug_ids_with_specifications,
                'has_branch':
                    bug.id in bug_ids_with_branches,
                'has_patch':
                    bug.latest_patch_uploaded is not None,
                }

        return badge_properties

    def getMultiple(self, task_ids):
        """See `IBugTaskSet`."""
        # Ensure we have a sequence of bug task IDs:
        task_ids = [int(task_id) for task_id in task_ids]
        # Query the database, returning the results in a dictionary:
        if len(task_ids) > 0:
            tasks = BugTask.select('id in %s' % sqlvalues(task_ids))
            return dict([(task.id, task) for task in tasks])
        else:
            return {}

    def findSimilar(self, user, summary, product=None, distribution=None,
                    sourcepackagename=None):
        """See `IBugTaskSet`."""
        if not summary:
            return EmptyResultSet()
        # Avoid circular imports.
        from lp.bugs.model.bug import Bug
        search_params = BugTaskSearchParams(user)
        constraint_clauses = ['BugTask.bug = Bug.id']
        if product:
            search_params.setProduct(product)
            constraint_clauses.append(
                'BugTask.product = %s' % sqlvalues(product))
        elif distribution:
            search_params.setDistribution(distribution)
            constraint_clauses.append(
                'BugTask.distribution = %s' % sqlvalues(distribution))
            if sourcepackagename:
                search_params.sourcepackagename = sourcepackagename
                constraint_clauses.append(
                    'BugTask.sourcepackagename = %s' % sqlvalues(
                        sourcepackagename))
        else:
            raise AssertionError('Need either a product or distribution.')

        search_params.fast_searchtext = nl_phrase_search(
            summary, Bug, ' AND '.join(constraint_clauses), ['BugTask'])
        return self.search(search_params, _noprejoins=True)

    def search(self, params, *args, **kwargs):
        """See `IBugTaskSet`.

        :param _noprejoins: Private internal parameter to BugTaskSet which
            disables all use of prejoins : consolidated from code paths that
            claim they were inefficient and unwanted.
        """
        # Prevent circular import problems.
        from lp.registry.model.product import Product
        from lp.bugs.model.bug import Bug
        from lp.bugs.model.bugtasksearch import search_bugs
        _noprejoins = kwargs.get('_noprejoins', False)
        if _noprejoins:
            eager_load = None
        else:
            def eager_load(rows):
                load_related(Bug, rows, ['bugID'])
                load_related(Product, rows, ['productID'])
                load_related(SourcePackageName, rows, ['sourcepackagenameID'])
        return search_bugs(eager_load, (params,) + args)

    def searchBugIds(self, params):
        """See `IBugTaskSet`."""
        from lp.bugs.model.bugtasksearch import search_bugs
        return search_bugs(None, [params], just_bug_ids=True).result_set

    def countBugs(self, user, contexts, group_on):
        """See `IBugTaskSet`."""
        # Circular fail.
        from lp.bugs.model.bugsummary import (
            BugSummary,
            get_bugsummary_filter_for_user,
            )
        conditions = []
        # Open bug statuses
        conditions.append(
            BugSummary.status.is_in(DB_UNRESOLVED_BUGTASK_STATUSES))
        # BugSummary does not include duplicates so no need to exclude.
        context_conditions = []
        for context in contexts:
            condition = removeSecurityProxy(
                context.getBugSummaryContextWhereClause())
            if condition is not False:
                context_conditions.append(condition)
        if not context_conditions:
            return {}
        conditions.append(Or(*context_conditions))
        # bugsummary by design requires either grouping by tag or excluding
        # non-null tags.
        # This is an awkward way of saying
        # if BugSummary.tag not in group_on:
        # - see bug 799602
        group_on_tag = False
        for column in group_on:
            if column is BugSummary.tag:
                group_on_tag = True
        if not group_on_tag:
            conditions.append(BugSummary.tag == None)
        else:
            conditions.append(BugSummary.tag != None)

        # Apply the privacy filter.
        store = IStore(BugSummary)
        user_with, user_where = get_bugsummary_filter_for_user(user)
        if user_with:
            store = store.with_(user_with)
        conditions.extend(user_where)

        sum_count = Sum(BugSummary.count)
        resultset = store.find(group_on + (sum_count,), *conditions)
        resultset.group_by(*group_on)
        resultset.having(sum_count != 0)
        # Ensure we have no order clauses.
        resultset.order_by()
        result = {}
        for row in resultset:
            result[row[:-1]] = row[-1]
        return result

    def getPrecachedNonConjoinedBugTasks(self, user, milestone_data):
        """See `IBugTaskSet`."""
        kwargs = {
            'orderby': ['status', '-importance', 'id'],
            'omit_dupes': True,
            }
        if IProjectGroupMilestoneTag.providedBy(milestone_data):
            # XXX: frankban 2012-01-05 bug=912370: excluding conjoined
            # bugtasks is not currently supported for milestone tags.
            kwargs.update({
                'exclude_conjoined_tasks': False,
                'milestone_tag': milestone_data,
                })
        else:
            kwargs.update({
                'exclude_conjoined_tasks': True,
                'milestone': milestone_data,
                })
        params = BugTaskSearchParams(user, **kwargs)
        return self.search(params)

    def createManyTasks(self, bug, owner, targets, validate_target=True,
                        status=None, importance=None, assignee=None,
                        milestone=None):
        """See `IBugTaskSet`."""
        if status is None:
            status = IBugTask['status'].default
        if importance is None:
            importance = IBugTask['importance'].default
        target_keys = []
        pillars = set()
        for target in targets:
            if validate_target:
                validate_new_target(bug, target)
            pillars.add(target.pillar)
            target_keys.append(bug_target_to_key(target))

        values = [
            (bug, owner, key['product'], key['productseries'],
             key['distribution'], key['distroseries'],
             key['sourcepackagename'], status, importance, assignee,
             milestone)
            for key in target_keys]
        tasks = create(
            (BugTask.bug, BugTask.owner, BugTask.product,
             BugTask.productseries, BugTask.distribution,
             BugTask.distroseries, BugTask.sourcepackagename, BugTask._status,
             BugTask.importance, BugTask.assignee, BugTask.milestone),
            values, get_objects=True)

        del get_property_cache(bug).bugtasks
        for bugtask in tasks:
            bugtask.updateTargetNameCache()
            if bugtask.conjoined_slave:
                bugtask._syncFromConjoinedSlave()
        removeSecurityProxy(bug)._reconcileAccess()
        return tasks

    def createTask(self, bug, owner, target, validate_target=True, status=None,
                   importance=None, assignee=None, milestone=None):
        """See `IBugTaskSet`."""
        # Create tasks for accepted nominations if this is a source
        # package addition. Distribution nominations are for all the
        # tasks.
        targets = [target]
        key = bug_target_to_key(target)
        if key['distribution'] is not None:
            for nomination in bug.getNominations(key['distribution']):
                if not nomination.isApproved():
                    continue
                targets.append(
                    nomination.distroseries.getSourcePackage(
                        key['sourcepackagename']))

        tasks = self.createManyTasks(
            bug, owner, targets, validate_target=validate_target,
            status=status, importance=importance, assignee=assignee,
            milestone=milestone)
        return [task for task in tasks if task.target == target][0]

    def getStatusCountsForProductSeries(self, user, product_series):
        """See `IBugTaskSet`."""
        if user is None:
            bug_privacy_filter = 'AND Bug.information_type IN %s' % (
                sqlvalues(PUBLIC_INFORMATION_TYPES))
        else:
            # Since the count won't reveal sensitive information, and
            # since the get_bug_privacy_filter() check for non-admins is
            # costly, don't filter those bugs at all.
            bug_privacy_filter = ''
        # The union is actually much faster than a LEFT JOIN with the
        # Milestone table, since postgres optimizes it to perform index
        # scans instead of sequential scans on the BugTask table.
        query = """
            SELECT
                status, COUNT(*)
            FROM (
                SELECT BugTask.status
                FROM BugTask
                    JOIN Bug ON BugTask.bug = Bug.id
                WHERE
                    BugTask.productseries = %(series)s
                    %(privacy)s
                UNION ALL
                SELECT BugTask.status
                FROM BugTask
                    JOIN Bug ON BugTask.bug = Bug.id
                    JOIN Milestone ON BugTask.milestone = Milestone.id
                WHERE
                    BugTask.productseries IS NULL
                    AND Milestone.productseries = %(series)s
                    %(privacy)s
                ) AS subquery
            GROUP BY status
            """
        query %= dict(
            series=quote(product_series),
            privacy=bug_privacy_filter)
        cur = cursor()
        cur.execute(query)
        return dict(
            (get_bugtask_status(status_id), count)
            for (status_id, count) in cur.fetchall())

    def findExpirableBugTasks(self, min_days_old, user,
                              bug=None, target=None, limit=None):
        """See `IBugTaskSet`.

        The list of Incomplete bugtasks is selected from products and
        distributions that use Launchpad to track bugs. To qualify for
        expiration, the bug and its bugtasks meet the follow conditions:

        1. The bug is inactive; the last update of the is older than
            Launchpad expiration age.
        2. The bug is not a duplicate.
        3. The bug does not have any other valid bugtasks.
        4. The bugtask belongs to a project with enable_bug_expiration set
           to True.
        5. The bugtask has the status Incomplete.
        6. The bugtask is not assigned to anyone.
        7. The bugtask does not have a milestone.

        Bugtasks cannot transition to Invalid automatically unless they meet
        all the rules stated above.

        This implementation returns the master of the master-slave conjoined
        pairs of bugtasks. Slave conjoined bugtasks are not included in the
        list because they can only be expired by calling the master bugtask's
        transitionToStatus() method. See 'Conjoined Bug Tasks' in
        c.l.doc/bugtasks.txt.

        Only bugtasks the specified user has permission to view are
        returned. The Janitor celebrity has permission to view all bugs.
        """
        from lp.bugs.model.bugtaskflat import BugTaskFlat
        from lp.bugs.model.bugtasksearch import get_bug_privacy_filter
        from lp.bugs.model.bugwatch import BugWatch

        statuses_not_preventing_expiration = [
            BugTaskStatus.INVALID, BugTaskStatus.INCOMPLETE,
            BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE,
            BugTaskStatus.WONTFIX]
        unexpirable_status_list = [
            status for status in BugTaskStatus.items
            if status not in statuses_not_preventing_expiration]
        RelatedBugTaskFlat = ClassAlias(BugTaskFlat)

        (target_joins, target_conds) = self._getTargetJoinAndClause(target)
        origin = IStore(BugTaskFlat).using(BugTaskFlat, *target_joins)
        conds = [
            BugTaskFlat.status.is_in(DB_INCOMPLETE_BUGTASK_STATUSES),
            BugTaskFlat.assignee == None,
            BugTaskFlat.milestone == None,
            BugTaskFlat.duplicateof == None,
            BugTaskFlat.date_last_updated <
                UTC_NOW - SQL("INTERVAL ?", (u'%d days' % min_days_old,)),
            Not(Exists(Select(
                1, tables=[BugWatch],
                where=[BugWatch.bugID == BugTaskFlat.bug_id]))),
            Not(Exists(Select(
                1, tables=[RelatedBugTaskFlat],
                where=And(
                    RelatedBugTaskFlat.bug_id == BugTaskFlat.bug_id,
                    RelatedBugTaskFlat.status.is_in(
                        unexpirable_status_list))))),
            ]
        conds.extend(target_conds)
        if bug is not None:
            conds.append(BugTaskFlat.bug_id == bug.id)
        # The janitor needs access to all bugs.
        if user != getUtility(ILaunchpadCelebrities).janitor:
            bug_privacy_filter = get_bug_privacy_filter(user)
            conds.append(bug_privacy_filter)

        ids = origin.find(BugTaskFlat.bugtask_id, conds)
        ids = ids.order_by(BugTaskFlat.date_last_updated)
        if limit is not None:
            ids = ids[:limit]

        return DecoratedResultSet(
            ids, lambda id: BugTask.get(id),
            pre_iter_hook=lambda rows: load(BugTask, rows))

    def _getTargetJoinAndClause(self, target):
        """Return a SQL join clause to a `BugTarget`.

        :param target: A supported BugTarget or None. The target param must
            be either a Distribution, DistroSeries, Product, or ProductSeries.
            If target is None, the clause joins BugTask to all the supported
            BugTarget tables.
        :raises NotImplementedError: If the target is an IProjectGroup,
            ISourcePackage, or an IDistributionSourcePackage.
        :raises AssertionError: If the target is not a known implementer of
            `IBugTarget`
        """
        from lp.bugs.model.bugtaskflat import BugTaskFlat
        from lp.registry.model.distribution import Distribution
        from lp.registry.model.distroseries import DistroSeries
        from lp.registry.model.product import Product
        from lp.registry.model.productseries import ProductSeries

        join_map = {
            Product: (
                LeftJoin(
                    ProductSeries,
                    ProductSeries.id == BugTaskFlat.productseries_id),
                LeftJoin(
                    Product,
                    Product.id.is_in(
                        (BugTaskFlat.product_id, ProductSeries.productID)))),
            Distribution: (
                LeftJoin(
                    DistroSeries,
                    DistroSeries.id == BugTaskFlat.distroseries_id),
                LeftJoin(
                    Distribution,
                    Distribution.id.is_in((
                        BugTaskFlat.distribution_id,
                        DistroSeries.distributionID)))),
            }
        pred_map = {
            Distribution: Distribution.enable_bug_expiration,
            Product: Product.enable_bug_expiration,
            }

        if IDistribution.providedBy(target):
            want = [Distribution]
            target_col = Distribution.id
        elif IDistroSeries.providedBy(target):
            want = [Distribution]
            target_col = DistroSeries.id
        elif IProduct.providedBy(target):
            want = [Product]
            target_col = Product.id
        elif IProductSeries.providedBy(target):
            want = [Product]
            target_col = ProductSeries.id
        elif target is None:
            want = [Product, Distribution]
            target_col = None
        elif (IProjectGroup.providedBy(target)
              or ISourcePackage.providedBy(target)
              or IDistributionSourcePackage.providedBy(target)):
            raise NotImplementedError(
                "BugTarget %s is not supported by ." % target)
        else:
            raise AssertionError("Unknown BugTarget type.")

        joins = []
        target_expirability_preds = []
        for cls in want:
            joins.extend(join_map[cls])
            target_expirability_preds.append(pred_map[cls])
        preds = [Or(*target_expirability_preds)]
        if target_col:
            preds.append(target_col == target.id)

        return (joins, preds)

    def getOpenBugTasksPerProduct(self, user, products):
        """See `IBugTaskSet`."""
        # Local import of Bug to avoid import loop.
        from lp.bugs.model.bugtaskflat import BugTaskFlat
        from lp.bugs.model.bugtasksearch import get_bug_privacy_filter

        result = IStore(BugTaskFlat).find(
            (BugTaskFlat.product_id, Count()),
            BugTaskFlat.status.is_in(DB_UNRESOLVED_BUGTASK_STATUSES),
            BugTaskFlat.duplicateof == None,
            BugTaskFlat.product_id.is_in(product.id for product in products),
            get_bug_privacy_filter(user),
            ).group_by(BugTaskFlat.product_id)
        # The result will return a list of product ids and counts,
        # which will be converted into key-value pairs in the dictionary.
        return dict(result)

    def getBugCountsForPackages(self, user, packages):
        """See `IBugTaskSet`."""
        distributions = sorted(
            set(package.distribution for package in packages),
            key=attrgetter('name'))
        counts = []
        for distribution in distributions:
            counts.extend(self._getBugCountsForDistribution(
                user, distribution, packages))
        return counts

    def _getBugCountsForDistribution(self, user, distribution, packages):
        """Get bug counts by package, belonging to the given distribution.

        See `IBugTask.getBugCountsForPackages` for more information.
        """
        from lp.bugs.model.bugtaskflat import BugTaskFlat
        from lp.bugs.model.bugtasksearch import get_bug_privacy_filter

        packages = [
            package for package in packages
            if package.distribution == distribution]
        package_name_ids = [
            package.sourcepackagename.id for package in packages]

        # The count of each package's open bugs matching each predicate
        # will be returned in the dict under the given name.
        sumexprs = [
            ('open',
             BugTaskFlat.status.is_in(DB_UNRESOLVED_BUGTASK_STATUSES)),
            ('open_critical',
             BugTaskFlat.importance == BugTaskImportance.CRITICAL),
            ('open_unassigned', BugTaskFlat.assignee == None),
            ('open_inprogress',
             BugTaskFlat.status == BugTaskStatus.INPROGRESS),
            ('open_high', BugTaskFlat.importance == BugTaskImportance.HIGH),
            ]

        result = IStore(BugTaskFlat).find(
            (BugTaskFlat.distribution_id, BugTaskFlat.sourcepackagename_id)
            + tuple(Sum(Cast(expr[1], 'integer')) for expr in sumexprs),
            BugTaskFlat.status.is_in(DB_UNRESOLVED_BUGTASK_STATUSES),
            BugTaskFlat.sourcepackagename_id.is_in(package_name_ids),
            BugTaskFlat.distribution == distribution,
            BugTaskFlat.duplicateof == None,
            get_bug_privacy_filter(user),
            ).group_by(
                BugTaskFlat.distribution_id, BugTaskFlat.sourcepackagename_id)

        # Map the returned counts back to their names and throw them in
        # the dict.
        packages_with_bugs = set()
        counts = []
        for row in result:
            distribution = getUtility(IDistributionSet).get(row[0])
            sourcepackagename = getUtility(ISourcePackageNameSet).get(row[1])
            source_package = distribution.getSourcePackage(sourcepackagename)
            packages_with_bugs.add((distribution, sourcepackagename))
            package_counts = dict(package=source_package)
            package_counts.update(zip(map(itemgetter(0), sumexprs), row[2:]))
            counts.append(package_counts)

        # Only packages with open bugs were included in the query. Let's
        # add the rest of the packages as well.
        all_packages = set(
            (distro_package.distribution, distro_package.sourcepackagename)
            for distro_package in packages)
        for distribution, sourcepackagename in all_packages.difference(
                packages_with_bugs):
            package_counts = dict(
                package=distribution.getSourcePackage(sourcepackagename))
            package_counts.update(
                zip(map(itemgetter(0), sumexprs), repeat(0)))
            counts.append(package_counts)

        return counts

    def getBugTaskTargetMilestones(self, bugtasks):
        from lp.registry.model.distribution import Distribution
        from lp.registry.model.distroseries import DistroSeries
        from lp.registry.model.milestone import Milestone
        from lp.registry.model.product import Product
        from lp.registry.model.productseries import ProductSeries
        store = Store.of(bugtasks[0])
        distro_ids = set()
        distro_series_ids = set()
        product_ids = set()
        product_series_ids = set()

        # Gather all the ids that might have milestones to preload for the
        # for the milestone vocabulary
        for task in bugtasks:
            task = removeSecurityProxy(task)
            distro_ids.add(task.distributionID)
            distro_series_ids.add(task.distroseriesID)
            product_ids.add(task.productID)
            if task.productseries:
                product_ids.add(task.productseries.productID)
            product_series_ids.add(task.productseriesID)

        distro_ids.discard(None)
        distro_series_ids.discard(None)
        product_ids.discard(None)
        product_series_ids.discard(None)

        milestones = store.find(
            Milestone,
            Milestone.active == True,
            Or(
                Milestone.distributionID.is_in(distro_ids),
                Milestone.distroseriesID.is_in(distro_series_ids),
                Milestone.productID.is_in(product_ids),
                Milestone.productseriesID.is_in(product_series_ids)))

        # Pull in all the related pillars
        list(store.find(
            Distribution, Distribution.id.is_in(distro_ids)))
        list(store.find(
            DistroSeries, DistroSeries.id.is_in(distro_series_ids)))
        list(store.find(
            Product, Product.id.is_in(product_ids)))
        list(store.find(
            ProductSeries, ProductSeries.id.is_in(product_series_ids)))

        return milestones
