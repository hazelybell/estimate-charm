# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces related to bugs."""

__metaclass__ = type

__all__ = [
    'ITranslationsOverview',
    'MalformedKarmaCacheData',
    ]

from zope.interface import Interface
from zope.schema import Int

from lp import _


class MalformedKarmaCacheData(Exception):
    """KarmaCache values are missing product or distribution identifier."""

class ITranslationsOverview(Interface):
    """Overview of Launchpad Translations component."""

    MINIMUM_SIZE = Int(
        title=_('Minimum relative weight for a product'),
        required=True, readonly=False)

    MAXIMUM_SIZE = Int(
        title=_('Maximum relative weight for a product'),
        required=True, readonly=False)

    def getMostTranslatedPillars(limit=50):
        """Get a list of products and distributions with most translations.

        :limit: A number of 'top' products to get.

        It returns a list of pairs (pillar, size), where `pillar` is
        either a product or a distribution, and size is the relative
        amount of contribution a pillar has received.
        """


class IProjectGroupTranslationsOverview(Interface):
    """Overview of translations for a project."""
