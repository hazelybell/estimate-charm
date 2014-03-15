# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""View support classes for the bazaar application."""

__metaclass__ = type

__all__ = [
    'BazaarApplicationView',
    'BazaarProductView',
    ]

from datetime import datetime

import bzrlib
from zope.component import getUtility

from lp.code.enums import CodeImportReviewStatus
from lp.code.interfaces.branch import (
    IBranchCloud,
    IBranchSet,
    )
from lp.code.interfaces.branchcollection import IAllBranches
from lp.code.interfaces.codeimport import ICodeImportSet
from lp.registry.interfaces.product import IProductSet
from lp.services.config import config
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    )
from lp.services.webapp.authorization import precache_permission_for_objects


class BazaarApplicationView(LaunchpadView):

    page_title = 'Launchpad Branches'

    @property
    def branch_count(self):
        """Return the number of public branches."""
        return getUtility(IAllBranches).visibleByUser(None).count()

    @property
    def product_count(self):
        return getUtility(IProductSet).getProductsWithBranches().count()

    @property
    def import_count(self):
        return getUtility(ICodeImportSet).search(
            review_status=CodeImportReviewStatus.REVIEWED).count()

    @property
    def bzr_version(self):
        return bzrlib.__version__

    def _precacheViewPermissions(self, branches):
        """Precache the launchpad.View permissions on the branches."""
        # XXX: TimPenhey 2009-06-08 bug=324546
        # Until there is an API to do this nicely, shove the launchpad.view
        # permission into the request cache directly.
        precache_permission_for_objects(
            self.request, 'launchpad.View', branches)
        return branches

    @cachedproperty
    def recently_changed_branches(self):
        """Return the five most recently changed branches."""
        return self._precacheViewPermissions(
            list(getUtility(IBranchSet).getRecentlyChangedBranches(
                    5, visible_by_user=self.user)))

    @cachedproperty
    def recently_imported_branches(self):
        """Return the five most recently imported branches."""
        return self._precacheViewPermissions(
            list(getUtility(IBranchSet).getRecentlyImportedBranches(
                    5, visible_by_user=self.user)))

    @cachedproperty
    def recently_registered_branches(self):
        """Return the five most recently registered branches."""
        return self._precacheViewPermissions(
            list(getUtility(IBranchSet).getRecentlyRegisteredBranches(
                    5, visible_by_user=self.user)))

    @cachedproperty
    def short_product_tag_cloud(self):
        """Show a preview of the product tag cloud."""
        return BazaarProductView(None, None).products(
            num_products=config.launchpad.code_homepage_product_cloud_size)


class ProductInfo:

    def __init__(self, name, commits, author_count, size, elapsed):
        self.name = name
        self.url = '/' + name
        self.commits = commits
        self.author_count = author_count
        self.size = size
        self.elapsed_since_commit = elapsed

    @property
    def tag_class(self):
        return "cloud-size-%s" % self.size

    @property
    def time_darkness(self):
        if self.elapsed_since_commit is None:
            return "light"
        if self.elapsed_since_commit.days < 7:
            return "dark"
        if self.elapsed_since_commit.days < 14:
            return "medium"
        return "light"

    @property
    def html_class(self):
        return "%s cloud-%s" % (self.tag_class, self.time_darkness)

    @property
    def html_title(self):
        if self.commits == 1:
            size = "1 commit"
        else:
            size = "%d commits" % self.commits
        if self.author_count == 1:
            who = "1 person"
        else:
            who = "%s people" % self.author_count
        if self.elapsed_since_commit.days == 0:
            commit = "last commit less than a day old"
        elif self.elapsed_since_commit.days == 1:
            commit = "last commit one day old"
        else:
            commit = (
                "last commit %d days old" % self.elapsed_since_commit.days)
        return "%s by %s, %s" % (size, who, commit)


class BazaarProjectsRedirect(LaunchpadView):
    """Redirect the user to /projects on the code rootsite."""

    def initialize(self):
        # Redirect to the caller to the new location.
        product_set = getUtility(IProductSet)
        redirect_url = canonical_url(product_set, rootsite="code")
        # Moved permanently.
        self.request.response.redirect(redirect_url, status=301)


class BazaarProductView(LaunchpadView):
    """Browser class for products gettable with Bazaar."""

    page_title = 'Projects with active branches'

    def _make_distribution_map(self, values, percentile_map):
        """Given some values and a map of percentiles to other values, return
        a function that will take a value in the same domain as 'values' and
        map it to a value in the 'percentile_map' dict.

        There *must* be a percentile_map entry for 1.0.
        """
        def constrained_minimum(xs, a):
            """Return the smallest value of 'xs' strictly bigger than 'a'."""
            return min(x for x in xs if x > a)

        cutoffs = percentile_map.keys()
        num_values = float(len(values))
        value_to_cutoffs = {}
        for index, value in enumerate(values):
            cutoff = constrained_minimum(cutoffs, (index / num_values))
            value_to_cutoffs[value] = percentile_map[cutoff]
        if num_values > 0 and 1 in percentile_map:
            value_to_cutoffs[values[-1]] = percentile_map[1]
        return value_to_cutoffs

    def products(self, num_products=None):
        # The product_info ends up sorted on product name, as the product name
        # is the first item of the tuple returned, and is guaranteed to be
        # unique by the sql query.
        product_info = sorted(
            getUtility(IBranchCloud).getProductsWithInfo(num_products))
        if len(product_info) == 0:
            return
        now = datetime.today()
        counts = sorted(zip(*product_info)[1])
        size_mapping = {
            0.2: 'smallest',
            0.4: 'small',
            0.6: 'medium',
            0.8: 'large',
            1.0: 'largest',
            }
        num_commits_to_size = self._make_distribution_map(
            counts, size_mapping)

        for name, commits, author_count, last_revision_date in product_info:
            size = num_commits_to_size[commits]
            elapsed = now - last_revision_date
            yield ProductInfo(name, commits, author_count, size, elapsed)
