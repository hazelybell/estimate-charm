# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'KarmaActionEditView',
    'KarmaActionSetNavigation',
    'KarmaContextTopContributorsView',
    ]

from operator import attrgetter

from zope.component import getUtility

from lp import _
from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    )
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.karma import (
    IKarmaAction,
    IKarmaActionSet,
    )
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    Navigation,
    )
from lp.services.webapp.publisher import LaunchpadView


TOP_CONTRIBUTORS_LIMIT = 20


class KarmaActionSetNavigation(Navigation):

    usedfor = IKarmaActionSet

    def traverse(self, name):
        return self.context.getByName(name)


class KarmaActionView(LaunchpadView):
    """View class for the index of karma actions."""

    page_title = 'Actions that give people karma'


class KarmaActionEditView(LaunchpadEditFormView):

    schema = IKarmaAction
    field_names = ["name", "category", "points", "title", "summary"]

    @property
    def label(self):
        """See `LaunchpadFormView`."""
        return 'Edit %s karma action' % self.context.title

    @property
    def page_title(self):
        """The page title."""
        return self.label

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(getUtility(IKarmaActionSet))

    @action(_("Change"), name="change")
    def change_action(self, action, data):
        self.updateContextFromData(data)
        self.next_url = self.cancel_url


class KarmaContextContributor:

    def __init__(self, person, karmavalue):
        self.person = person
        self.karmavalue = karmavalue


class KarmaContextTopContributorsView(LaunchpadView):
    """List this KarmaContext's top contributors."""

    @property
    def page_title(self):
        return "Top %s Contributors" % self.context.title

    def initialize(self):
        context = self.context
        if IProduct.providedBy(context):
            self.context_name = 'Project'
        elif IDistribution.providedBy(context):
            self.context_name = 'Distribution'
        elif IProjectGroup.providedBy(context):
            self.context_name = 'Project Group'
        else:
            raise AssertionError(
                "Context is not a Product, Project group or Distribution: %r"
                % context)

    def _getTopContributorsWithLimit(self, limit=None):
        results = self.context.getTopContributors(limit=limit)
        contributors = [KarmaContextContributor(person, karmavalue)
                        for person, karmavalue in results]
        return sorted(
            contributors, key=attrgetter('karmavalue'), reverse=True)

    def getTopContributors(self):
        return self._getTopContributorsWithLimit(limit=TOP_CONTRIBUTORS_LIMIT)

    def getTopFiveContributors(self):
        return self._getTopContributorsWithLimit(limit=5)

    @cachedproperty
    def top_contributors_by_category(self):
        contributors_by_category = {}
        limit = TOP_CONTRIBUTORS_LIMIT
        results = self.context.getTopContributorsGroupedByCategory(
            limit=limit)
        for category, people_and_karma in results.items():
            contributors = []
            for person, karmavalue in people_and_karma:
                contributors.append(KarmaContextContributor(
                    person, karmavalue))
            contributors.sort(key=attrgetter('karmavalue'), reverse=True)
            contributors_by_category[category.title] = contributors
        return contributors_by_category

    @property
    def sorted_categories(self):
        return sorted(self.top_contributors_by_category.keys())
