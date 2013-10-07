# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug domain vocabularies"""

__metaclass__ = type
__all__ = [
    'UsesBugsDistributionVocabulary',
    'BugNominatableDistroSeriesVocabulary',
    'BugNominatableProductSeriesVocabulary',
    'BugNominatableSeriesVocabulary',
    'BugTaskMilestoneVocabulary',
    'BugTrackerVocabulary',
    'BugVocabulary',
    'BugWatchVocabulary',
    'DistributionUsingMaloneVocabulary',
    'project_products_using_malone_vocabulary_factory',
    'UsesBugsDistributionVocabulary',
    'WebBugTrackerVocabulary',
    ]

from operator import attrgetter

from sqlobject import (
    CONTAINSSTRING,
    OR,
    )
from storm.expr import (
    And,
    Or,
    )
from zope.component import getUtility
from zope.interface import implements
from zope.schema.interfaces import (
    IVocabulary,
    IVocabularyTokenized,
    )
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )
from zope.security.proxy import removeSecurityProxy

from lp.app.browser.stringformatter import FormattersAPI
from lp.app.enums import ServiceUsage
from lp.bugs.interfaces.bugtask import (
    IBugTask,
    IBugTaskSet,
    )
from lp.bugs.interfaces.bugtracker import BugTrackerType
from lp.bugs.model.bug import Bug
from lp.bugs.model.bugtracker import BugTracker
from lp.bugs.model.bugwatch import BugWatch
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.registry.model.distribution import Distribution
from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.productseries import ProductSeries
from lp.registry.vocabularies import DistributionVocabulary
from lp.services.database.interfaces import IStore
from lp.services.helpers import (
    ensure_unicode,
    shortlist,
    )
from lp.services.webapp.escaping import (
    html_escape,
    structured,
    )
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.vocabulary import (
    CountableIterator,
    IHugeVocabulary,
    NamedSQLObjectVocabulary,
    SQLObjectVocabularyBase,
    )


class UsesBugsDistributionVocabulary(DistributionVocabulary):
    """Distributions that use Launchpad to track bugs.

    If the context is a distribution, it is always included in the
    vocabulary. Historic data is not invalidated if a distro stops
    using Launchpad to track bugs. This vocabulary offers the correct
    choices of distributions at this moment.
    """

    def __init__(self, context=None):
        super(UsesBugsDistributionVocabulary, self).__init__(context=context)
        self.distribution = IDistribution(self.context, None)

    @property
    def _filter(self):
        if self.distribution is None:
            distro_id = 0
        else:
            distro_id = self.distribution.id
        return OR(
            self._table.q.official_malone == True,
            self._table.id == distro_id)


class BugVocabulary(SQLObjectVocabularyBase):

    _table = Bug
    _orderBy = 'id'


class BugTrackerVocabulary(SQLObjectVocabularyBase):
    """All web and email based external bug trackers."""
    displayname = 'Select a bug tracker'
    step_title = 'Search'
    implements(IHugeVocabulary)
    _table = BugTracker
    _filter = True
    _orderBy = 'title'
    _order_by = [BugTracker.title]

    def toTerm(self, obj):
        """See `IVocabulary`."""
        return SimpleTerm(obj, obj.name, obj.title)

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        result = IStore(self._table).find(
            self._table,
            self._filter,
            BugTracker.name == token).one()
        if result is None:
            raise LookupError(token)
        return self.toTerm(result)

    def search(self, query, vocab_filter=None):
        """Search for web bug trackers."""
        query = ensure_unicode(query).lower()
        results = IStore(self._table).find(
            self._table, And(
            self._filter,
            BugTracker.active == True,
            Or(
                CONTAINSSTRING(BugTracker.name, query),
                CONTAINSSTRING(BugTracker.title, query),
                CONTAINSSTRING(BugTracker.summary, query),
                CONTAINSSTRING(BugTracker.baseurl, query))))
        results = results.order_by(self._order_by)
        return results

    def searchForTerms(self, query=None, vocab_filter=None):
        """See `IHugeVocabulary`."""
        results = self.search(query, vocab_filter)
        return CountableIterator(results.count(), results, self.toTerm)


class WebBugTrackerVocabulary(BugTrackerVocabulary):
    """All web-based bug tracker types."""
    _filter = BugTracker.bugtrackertype != BugTrackerType.EMAILADDRESS


def project_products_using_malone_vocabulary_factory(context):
    """Return a vocabulary containing a project's products using Malone."""
    project = IProjectGroup(context)
    return SimpleVocabulary([
        SimpleTerm(product, product.name, title=product.displayname)
        for product in project.products
        if product.bug_tracking_usage == ServiceUsage.LAUNCHPAD])


class BugWatchVocabulary(SQLObjectVocabularyBase):
    _table = BugWatch

    def __iter__(self):
        assert IBugTask.providedBy(self.context), (
            "BugWatchVocabulary expects its context to be an IBugTask.")
        bug = self.context.bug

        for watch in bug.watches:
            yield self.toTerm(watch)

    def toTerm(self, watch):
        if watch.url.startswith('mailto:'):
            user = getUtility(ILaunchBag).user
            if user is None:
                title = html_escape(
                    FormattersAPI(watch.bugtracker.title).obfuscate_email())
            else:
                url = watch.url
                if url in watch.bugtracker.title:
                    title = html_escape(watch.bugtracker.title).replace(
                        html_escape(url),
                        structured(
                            '<a href="%s">%s</a>', url, url).escapedtext)
                else:
                    title = structured(
                        '%s &lt;<a href="%s">%s</a>&gt;',
                        watch.bugtracker.title, url, url[7:]).escapedtext
        else:
            title = structured(
                '%s <a href="%s">#%s</a>',
                watch.bugtracker.title, watch.url,
                watch.remotebug).escapedtext

        # title is already HTML-escaped.
        return SimpleTerm(watch, watch.id, title)


class DistributionUsingMaloneVocabulary:
    """All the distributions that uses Malone officially."""

    implements(IVocabulary, IVocabularyTokenized)

    _orderBy = 'displayname'

    def __init__(self, context=None):
        self.context = context

    def __iter__(self):
        """Return an iterator which provides the terms from the vocabulary."""
        distributions_using_malone = Distribution.selectBy(
            official_malone=True, orderBy=self._orderBy)
        for distribution in distributions_using_malone:
            yield self.getTerm(distribution)

    def __len__(self):
        return Distribution.selectBy(official_malone=True).count()

    def __contains__(self, obj):
        return (IDistribution.providedBy(obj)
                and obj.bug_tracking_usage == ServiceUsage.LAUNCHPAD)

    def getTerm(self, obj):
        if obj not in self:
            raise LookupError(obj)
        return SimpleTerm(obj, obj.name, obj.displayname)

    def getTermByToken(self, token):
        found_dist = Distribution.selectOneBy(
            name=token, official_malone=True)
        if found_dist is None:
            raise LookupError(token)
        return self.getTerm(found_dist)


def BugNominatableSeriesVocabulary(context=None):
    """Return a nominatable series vocabulary."""
    if getUtility(ILaunchBag).distribution:
        return BugNominatableDistroSeriesVocabulary(
            context, getUtility(ILaunchBag).distribution)
    else:
        assert getUtility(ILaunchBag).product
        return BugNominatableProductSeriesVocabulary(
            context, getUtility(ILaunchBag).product)


class BugNominatableSeriesVocabularyBase(NamedSQLObjectVocabulary):
    """Base vocabulary class for series for which a bug can be nominated."""

    def __iter__(self):
        bug = self.context.bug

        all_series = self._getNominatableObjects()

        for series in sorted(all_series, key=attrgetter("displayname")):
            if bug.canBeNominatedFor(series):
                yield self.toTerm(series)

    def toTerm(self, obj):
        return SimpleTerm(obj, obj.name, obj.name.capitalize())

    def getTermByToken(self, token):
        obj = self._queryNominatableObjectByName(token)
        if obj is None:
            raise LookupError(token)

        return self.toTerm(obj)

    def _getNominatableObjects(self):
        """Return the series objects that the bug can be nominated for."""
        raise NotImplementedError

    def _queryNominatableObjectByName(self, name):
        """Return the series object with the given name."""
        raise NotImplementedError


class BugNominatableProductSeriesVocabulary(
    BugNominatableSeriesVocabularyBase):
    """The product series for which a bug can be nominated."""

    _table = ProductSeries

    def __init__(self, context, product):
        BugNominatableSeriesVocabularyBase.__init__(self, context)
        self.product = product

    def _getNominatableObjects(self):
        """See BugNominatableSeriesVocabularyBase."""
        return shortlist(self.product.series)

    def _queryNominatableObjectByName(self, name):
        """See BugNominatableSeriesVocabularyBase."""
        return self.product.getSeries(name)


class BugNominatableDistroSeriesVocabulary(
    BugNominatableSeriesVocabularyBase):
    """The distribution series for which a bug can be nominated."""

    _table = DistroSeries

    def __init__(self, context, distribution):
        BugNominatableSeriesVocabularyBase.__init__(self, context)
        self.distribution = distribution

    def _getNominatableObjects(self):
        """Return all non-obsolete distribution series"""
        return [
            series for series in shortlist(self.distribution.series)
            if series.status != SeriesStatus.OBSOLETE]

    def _queryNominatableObjectByName(self, name):
        """See BugNominatableSeriesVocabularyBase."""
        return self.distribution.getSeries(name)


def milestone_matches_bugtask(milestone, bugtask):
    """ Return True if the milestone can be set against this bugtask."""
    bug_target = bugtask.target
    naked_milestone = removeSecurityProxy(milestone)

    if IProduct.providedBy(bug_target):
        return bugtask.product.id == naked_milestone.productID
    elif IProductSeries.providedBy(bug_target):
        return bugtask.productseries.product.id == naked_milestone.productID
    elif (IDistribution.providedBy(bug_target) or
          IDistributionSourcePackage.providedBy(bug_target)):
        return bugtask.distribution.id == naked_milestone.distributionID
    elif (IDistroSeries.providedBy(bug_target) or
          ISourcePackage.providedBy(bug_target)):
        return bugtask.distroseries.id == naked_milestone.distroseriesID
    return False


class BugTaskMilestoneVocabulary:
    """Milestones for a set of bugtasks.

    This vocabulary supports the optional preloading and caching of milestones
    in order to avoid repeated database queries.
    """

    implements(IVocabulary, IVocabularyTokenized)

    def __init__(self, default_bugtask=None, milestones=None):
        assert default_bugtask is None or IBugTask.providedBy(default_bugtask)
        self.default_bugtask = default_bugtask
        self._milestones = None
        if milestones is not None:
            self._milestones = dict(
                (str(milestone.id), milestone) for milestone in milestones)

    def _load_milestones(self, bugtask):
        # If the milestones have not already been cached, load them for the
        # specified bugtask.
        if self._milestones is None:
            bugtask_set = getUtility(IBugTaskSet)
            milestones = list(
                bugtask_set.getBugTaskTargetMilestones([bugtask]))
            self._milestones = dict(
                (str(milestone.id), milestone) for milestone in milestones)
        return self._milestones

    @property
    def milestones(self):
        return self._load_milestones(self.default_bugtask)

    def visible_milestones(self, bugtask=None):
        return self._get_milestones(bugtask)

    def _get_milestones(self, bugtask=None):
        """All milestones for the specified bugtask."""
        bugtask = bugtask or self.default_bugtask
        if bugtask is None:
            return []

        self._load_milestones(bugtask)
        milestones = [milestone
                for milestone in self._milestones.values()
                if milestone_matches_bugtask(milestone, bugtask)]

        if (bugtask.milestone is not None and
            bugtask.milestone not in milestones):
            # Even if we inactivate a milestone, a bugtask might still be
            # linked to it. Include such milestones in the vocabulary to
            # ensure that the +editstatus page doesn't break.
            milestones.append(bugtask.milestone)
        return milestones

    def getTerm(self, value):
        """See `IVocabulary`."""
        if value not in self:
            raise LookupError(value)
        return self.toTerm(value)

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        try:
            return self.toTerm(self.milestones[str(token)])
        except:
            raise LookupError(token)

    def __len__(self):
        """See `IVocabulary`."""
        return len(self._get_milestones())

    def __iter__(self):
        """See `IVocabulary`."""
        return iter(
            [self.toTerm(milestone) for milestone in self._get_milestones()])

    def toTerm(self, obj):
        """See `IVocabulary`."""
        return SimpleTerm(obj, obj.id, obj.displayname)

    def __contains__(self, obj):
        """See `IVocabulary`."""
        return obj in self._get_milestones()
