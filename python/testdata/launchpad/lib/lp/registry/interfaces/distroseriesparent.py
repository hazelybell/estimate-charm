# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""DistroSeriesParent interface."""

__metaclass__ = type

__all__ = [
    'IDistroSeriesParent',
    'IDistroSeriesParentSet',
    ]

from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Bool,
    Choice,
    Int,
    )

from lp import _
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.pocket import PackagePublishingPocket


class IDistroSeriesParent(Interface):
    """`DistroSeriesParent` interface."""

    id = Int(title=_('ID'), required=True, readonly=True)

    derived_series = Reference(
        IDistroSeries, title=_("Derived Series"), required=True,
        description=_("The derived distribution series."))

    parent_series = Reference(
        IDistroSeries, title=_("Parent Series"), required=True,
        description=_("The parent distribution series."))

    initialized = Bool(
        title=_("Initialized"), required=True,
        description=_(
            "Whether or not the derived_series has been populated with "
            "packages from its parent_series."))

    is_overlay = Bool(
        title=_("Is this relationship an overlay?"), required=True,
        default=False)

    pocket = Choice(
        title=_("The pocket for this overlay"), required=False,
        vocabulary=PackagePublishingPocket)

    component = Choice(
        title=_("The component for this overlay"), required=False,
        vocabulary='Component')

    ordering = Int(
            title=_("Parent build dependency ordering"), required=False,
            default=1,
            description=_(
                "Parents are ordered in decreasing order of preference "
                "starting from 1."))


class IDistroSeriesParentSet(Interface):
    """`DistroSeriesParentSet` interface."""

    def new(derived_series, parent_series, initialized, is_overlay=False,
            pocket=None, component=None, ordering=1):
        """Create a new `DistroSeriesParent`."""

    def getByDerivedSeries(derived_series):
        """Get the `DistroSeriesParent` by derived series.

        :param derived_series: An `IDistroseries`
        """

    def getByParentSeries(parent_series):
        """Get the `DistroSeriesParent` by parent series.

        :param parent_series: An `IDistroseries`
        """

    def getByDerivedAndParentSeries(derived_series, parent_series):
        """Get the `DistroSeriesParent` by derived and parent series.

        :param derived_series: The derived `IDistroseries`
        :param parent_series: The parent `IDistroseries`
        """

    def getFlattenedOverlayTree(derived_series):
        """Get the list of DistroSeriesParents corresponding to the
        flattened overlay tree.

        :param parent_series: An `IDistroseries`.
        :return: A list of `IDistroSeriesParents`.

        For instance, given the following structure:

                     series               type of relation:
                       |                    |           |
            -----------------------         |           o
            |          |          |         |           |
            o          o          |      no overlay  overlay
            |          |          |
        parent1    parent2    parent3

        The result would be:
        [dsp(series, parent1), dsp(series, parent2)]
        """
