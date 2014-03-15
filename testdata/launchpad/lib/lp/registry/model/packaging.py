# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['Packaging', 'PackagingUtil']

from lazr.lifecycle.event import (
    ObjectCreatedEvent,
    ObjectDeletedEvent,
    )
from sqlobject import ForeignKey
from zope.component import getUtility
from zope.event import notify
from zope.interface import implements
from zope.security.interfaces import Unauthorized

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.errors import CannotPackageProprietaryProduct
from lp.registry.interfaces.packaging import (
    IPackaging,
    IPackagingUtil,
    PackagingType,
    )
from lp.registry.interfaces.person import validate_public_person
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase
from lp.services.webapp.interfaces import ILaunchBag


class Packaging(SQLBase):
    """A Packaging relating a SourcePackageName in DistroSeries and a Product.
    """

    implements(IPackaging)

    _table = 'Packaging'

    productseries = ForeignKey(foreignKey="ProductSeries",
                               dbName="productseries",
                               notNull=True)
    sourcepackagename = ForeignKey(foreignKey="SourcePackageName",
                                   dbName="sourcepackagename",
                                   notNull=True)
    distroseries = ForeignKey(foreignKey='DistroSeries',
                               dbName='distroseries',
                               notNull=True)
    packaging = EnumCol(dbName='packaging', notNull=True,
                        enum=PackagingType)
    datecreated = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person,
        notNull=False, default=DEFAULT)

    @property
    def sourcepackage(self):
        from lp.registry.model.sourcepackage import SourcePackage
        return SourcePackage(distroseries=self.distroseries,
            sourcepackagename=self.sourcepackagename)

    def __init__(self, **kwargs):
        super(Packaging, self).__init__(**kwargs)
        notify(ObjectCreatedEvent(self))

    def userCanDelete(self):
        """See `IPackaging`."""
        user = getUtility(ILaunchBag).user
        if user is None:
            return False
        admin = getUtility(ILaunchpadCelebrities).admin
        registry_experts = (getUtility(ILaunchpadCelebrities).registry_experts)
        if (not user.is_probationary
            or user.inTeam(self.productseries.product.owner)
            or user.canAccess(self.sourcepackage, 'setBranch')
            or user.inTeam(registry_experts) or user.inTeam(admin)):
            return True
        return False

    def destroySelf(self):
        if not self.userCanDelete():
            raise Unauthorized(
                'Only the person who created the packaging and package '
                'maintainers can delete it.')
        notify(ObjectDeletedEvent(self))
        super(Packaging, self).destroySelf()


class PackagingUtil:
    """Utilities for Packaging."""
    implements(IPackagingUtil)

    @classmethod
    def createPackaging(cls, productseries, sourcepackagename,
                        distroseries, packaging, owner):
        """See `IPackaging`.

        Raises an assertion error if there is already packaging for
        the sourcepackagename in the distroseries.
        """
        if cls.packagingEntryExists(sourcepackagename, distroseries):
            raise AssertionError(
                "A packaging entry for %s in %s already exists." %
                (sourcepackagename.name, distroseries.name))
        # XXX: AaronBentley: 2012-08-12 bug=1066063 Cannot adapt ProductSeries
        # to IInformationType.
        # The line below causes a failure of
        # lp.registry.tests.test_distroseries.TestDistroSeriesPackaging.
        # test_getPrioritizedPackagings_bug_tracker because
        # productseries.product loses all set permissions.
        # info_type = IInformationType(productseries).information_type
        info_type = productseries.product.information_type
        if info_type != InformationType.PUBLIC:
            raise CannotPackageProprietaryProduct(
                "Only Public project series can be packaged, not %s."
                % info_type.title)
        return Packaging(productseries=productseries,
                         sourcepackagename=sourcepackagename,
                         distroseries=distroseries,
                         packaging=packaging,
                         owner=owner)

    def deletePackaging(self, productseries, sourcepackagename, distroseries):
        """See `IPackaging`."""
        packaging = Packaging.selectOneBy(
            productseries=productseries,
            sourcepackagename=sourcepackagename,
            distroseries=distroseries)
        assert packaging is not None, (
            "Tried to delete non-existent Packaging: "
            "productseries=%s/%s, sourcepackagename=%s, distroseries=%s/%s"
            % (productseries.name, productseries.product.name,
               sourcepackagename.name,
               distroseries.parent.name, distroseries.name))
        packaging.destroySelf()

    @staticmethod
    def packagingEntryExists(sourcepackagename, distroseries,
                             productseries=None):
        """See `IPackaging`."""
        criteria = dict(
            sourcepackagename=sourcepackagename,
            distroseries=distroseries)
        if productseries is not None:
            criteria['productseries'] = productseries
        result = Packaging.selectOneBy(**criteria)
        if result is None:
            return False
        return True
