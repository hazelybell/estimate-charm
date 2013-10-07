# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Packaging interfaces."""

__metaclass__ = type

__all__ = [
    'IPackaging',
    'IPackagingUtil',
    'PackagingType',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Datetime,
    Int,
    )

from lp import _
from lp.registry.interfaces.role import IHasOwner


class PackagingType(DBEnumeratedType):
    """Source packages.

    Source packages include software from one or more Upstream open source
    projects. This schema shows the relationship between a source package
    and the upstream open source products that it might incorporate. This
    schema is used in the Packaging table.
    """

    PRIME = DBItem(1, """
        Primary Project

        This is the primary project packaged in this source package. For
        example, a source package "apache2" would have a "prime" packaging
        relationship with the "apache2" product from the Apache Project.
        The project and package don't have to have the same name.
        """)

    INCLUDES = DBItem(2, """
        SourcePackage Includes Project

        This source package includes some part or all of the project. For
        example, the "cadaver" source package has an "includes" packaging
        relationship with the libneon project.
        """)


class IPackaging(IHasOwner):
    """
    A Packaging entry. It relates a SourcePackageName, DistroSeries
    and ProductSeries, with a packaging type. So, for example, we use this
    table to specify that the mozilla-firefox package in hoary is actually a
    primary packaging of firefox 1.0 series releases.
    """
    id = Int(title=_('Packaging ID'))

    productseries = Choice(
        title=_('Upstream Series'), required=True,
        vocabulary="ProductSeries", description=_(
        "The series for this source package. The same distribution "
        "release may package two different series of the same project as "
        "different source packages. For example: python2.4 and python2.5"))

    sourcepackagename = Choice(
        title=_("Source Package Name"), required=True,
        vocabulary='SourcePackageName')

    distroseries = Choice(
        title=_("Distribution Series"), required=True,
        vocabulary='DistroSeries')

    packaging = Choice(
        title=_('Packaging'), required=True, vocabulary=PackagingType,
        description=_(
            "Is the project the primary content of the source package, "
            "or does the source package include the work of other projects?"))

    datecreated = Datetime(
        title=_('Date Created'), required=True, readonly=True)

    sourcepackage = Attribute(_("A source package that is constructed from "
        "the distroseries and sourcepackagename of this packaging record."))

    def userCanDelete():
        """True, if the current user is allowed to delete this packaging,
        else False.

        Non-probationary users can delete packaging links that they believe
        connect Ubuntu to bogus data.
        """


class IPackagingUtil(Interface):
    """Utilities to handle Packaging."""

    def createPackaging(productseries, sourcepackagename,
                        distroseries, packaging, owner):
        """Create Packaging entry."""

    def deletePackaging(productseries, sourcepackagename, distroseries):
        """Delete a packaging entry."""

    def packagingEntryExists(sourcepackagename, distroseries,
                             productseries=None):
        """Does this packaging entry already exists?

        A sourcepackagename is unique to a distroseries. Passing the
        productseries argument verifies that the packaging entry exists and
        that it is for the productseries
        """
