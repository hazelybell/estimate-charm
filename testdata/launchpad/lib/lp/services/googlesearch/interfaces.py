# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for searching and working with results."""

__metaclass__ = type

__all__ = [
    'ISearchResult',
    'ISearchResults',
    'ISearchService',
    'GoogleResponseError',
    'GoogleWrongGSPVersion',
    ]

from zope.interface import Interface
from zope.schema import (
    Int,
    Text,
    TextLine,
    URI,
    )

from lp import _


class ISearchResult(Interface):
    """An item that matches a search query."""

    title = TextLine(
        title=_('Title'), required=True,
        description=_('The title of the item.'))
    url = URI(
        title=_('URL'), required=True,
        description=_('The full URL of the item.'))
    summary = Text(
        title=_('Title'), required=True,
        description=_(
            'A summary of the item, possibly with information about why the '
            'item is considered to be a valid result for a search.'))


class ISearchResults(Interface):
    """A collection of `ISearchResult` items that match a search query."""

    total = Int(
        title=_('Total'), required=True,
        description=_(
            'The total number of items that matched a search. This '
            'collection may be a slice of the total items because the '
            'search service returns the results in batches.'))
    start = Int(
        title=_('Start'), required=True,
        description=_(
            'The index of the first item in the collection relative to the '
            'total number of items. The collection may only contain a slice '
            'of the total search results.'))

    def __len__():
        """The number of items in the collection returned by the search.

        This number may be much smaller than the total matches because the
        search service may batch the items.
        """

    def __getitem__(index):
        """Return the item at index in the collection."""

    def __iter__():
        """Iterate over the items in the collection."""


class GoogleWrongGSPVersion(ValueError):
    """Raised when the content is not parsable Google Search Protocol XML."""


class GoogleResponseError(SyntaxError):
    """Raised when Google's response is not contain valid XML."""


class ISearchService(Interface):
    """A service that can return an `ISearchResults` for a query."""

    def search(terms, start=0):
        """Search a source for items that match the terms and.

        :param terms: A string of terms understood by the search service.
        :param start: The index of the first item to return in the
            `ISearchResults` collection. The search service may limit the
            number of items in the results. The start parameter can be used
            to page though batches of `ISearchResults`.
        :return: `ISearchResults`.
        """
