# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface for things that contains a collection of FAQs."""

__metaclass__ = type

__all__ = [
    'FAQSort',
    'IFAQCollection',
    'ISearchFAQsForm',
    ]


from lazr.enum import (
    EnumeratedType,
    Item,
    )
from zope.interface import Interface
from zope.schema import TextLine

from lp import _


class FAQSort(EnumeratedType):
    """An enumeration of the valid FAQ search sort order.

    This enumeration is part of the IFAQCollection.searchFAQs() API. The
    titles are formatted for nice display in browser code.
    """

    RELEVANCY = Item("""
    by relevancy

    Sort by relevancy of the FAQ toward the search text.
    """)

    NEWEST_FIRST = Item("""
    newest first

    Sort FAQs from newest to oldest.
    """)

    OLDEST_FIRST = Item("""
    oldest first

    Sort FAQs from oldset to newest.
    """)


class IFAQCollection(Interface):
    """Interface provided by collection of FAQs.

    This interface allows for retrieving and searching for FAQs. The
    more specific `IFAQTarget` interface is used for objects that directly
    contain the FAQ.
    """

    def getFAQ(id):
        """Return the `IFAQ` in this collection with the requested id.

        :return: The `IFAQ` with the requested id or None if there is no
            document with that id.
        """

    def searchFAQs(search_text=None, owner=None, sort=None):
        """Return the FAQs in the collection that matches the search criteria.

        :param search_text: A string that is matched against the FAQ title,
            keywords and content. If None, the search_text is not included as
            a filter criteria.

        :param owner: A person that is matched against the owner of the FAQ.
            If None, owner is not included as a filter criteria.

        :param sort:  One value from the FAQSort enumeration. If None, a
            default value is used. When there is a search_text value, the
            default is to sort by RELEVANCY, otherwise results are sorted
            NEWEST_FIRST.
        """


# The next schema is only used by browser/faqcollection.py and should really
# live there. See Bug #66950.
class ISearchFAQsForm(Interface):
    """Schema for the search FAQs form."""

    search_text = TextLine(title=_('Search text'), required=False)
