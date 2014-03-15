# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Decorated model objects used in the browser code."""

__metaclass__ = type
__all__ = [
    'DecoratedBranch',
    ]

from lazr.delegates import delegates
from zope.interface import implements

from lp.app.interfaces.informationtype import IInformationType
from lp.app.interfaces.launchpad import IPrivacy
from lp.code.interfaces.branch import (
    BzrIdentityMixin,
    IBranch,
    )
from lp.services.propertycache import cachedproperty


class DecoratedBranch(BzrIdentityMixin):
    """Wrap a number of the branch accessors to cache results.

    This avoids repeated db queries.
    """
    implements(IPrivacy)
    delegates([IBranch, IInformationType], 'branch')

    def __init__(self, branch):
        self.branch = branch

    @property
    def displayname(self):
        """Override the default model property.

        If left to the underlying model, it would call the bzr_identity on the
        underlying branch rather than the cached bzr_identity on the decorated
        branch.  And that would cause two database queries.
        """
        return self.bzr_identity

    @cachedproperty
    def bzr_identity(self):
        """Cache the result of the bzr identity.

        The property is defined in the bzrIdentityMixin class.  This uses the
        associatedProductSeries and associatedSuiteSourcePackages methods.
        """
        return super(DecoratedBranch, self).bzr_identity

    @cachedproperty
    def is_series_branch(self):
        """A simple property to see if there are any series links."""
        # True if linked to a product series or suite source package.
        return (
            len(self.associated_product_series) > 0 or
            len(self.suite_source_packages) > 0)

    def associatedProductSeries(self):
        """Override the IBranch.associatedProductSeries."""
        return self.associated_product_series

    def associatedSuiteSourcePackages(self):
        """Override the IBranch.associatedSuiteSourcePackages."""
        return self.suite_source_packages

    @cachedproperty
    def associated_product_series(self):
        """Cache the realized product series links."""
        return list(self.branch.associatedProductSeries())

    @cachedproperty
    def suite_source_packages(self):
        """Cache the realized suite source package links."""
        return list(self.branch.associatedSuiteSourcePackages())

    @cachedproperty
    def upgrade_pending(self):
        """Cache the result as the property hits the database."""
        return self.branch.upgrade_pending

    @cachedproperty
    def subscriptions(self):
        """Cache the realized branch subscription objects."""
        return list(self.branch.subscriptions)

    def hasSubscription(self, user):
        """Override the default branch implementation.

        The default implementation hits the database.  Since we have a full
        list of subscribers anyway, a simple check over the list is
        sufficient.
        """
        if user is None:
            return False
        return user.id in [sub.personID for sub in self.subscriptions]

    @cachedproperty
    def latest_revisions(self):
        """Cache the query result.

        When a tal:repeat is used, the method is called twice.  Firstly to
        check that there is something to iterate over, and secondly for the
        actual iteration.  Without the cached property, the database is hit
        twice.
        """
        return list(self.branch.latest_revisions())
