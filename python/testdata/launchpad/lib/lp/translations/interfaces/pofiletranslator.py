# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'IPOFileTranslator',
    'IPOFileTranslatorSet',
    ]


from zope.interface import Interface
from zope.schema import (
    Datetime,
    Int,
    Object,
    )

from lp import _
from lp.registry.interfaces.person import IPerson
from lp.translations.interfaces.pofile import IPOFile


class IPOFileTranslator(Interface):
    """Represents contributions from people to `POFile`s."""

    id = Int(title=_("ID"), readonly=True, required=True)

    person = Object(
        title=_(u"The `Person` whose contribution this record represents."),
        required=True, readonly=True, schema=IPerson)

    pofile = Object(
        title=_(u"The `POFile` modified by the translator."), required=True,
        readonly=True, schema=IPOFile)

    date_last_touched = Datetime(
        title=_(u"When the latest translation message was added."),
        required=True, readonly=True)


class IPOFileTranslatorSet(Interface):
    """Interface representing the set of `IPOFileTranslator`records.

    You won't find a "new" method here.  POFileTranslator records are
    created directly in the database by a trigger that watches for
    translation updates.
    """

    def prefetchPOFileTranslatorRelations(pofiletranslators):
        """Batch-prefetch objects attached to given `POFileTranslator`s.

        Fetches a large amount of data relevant to rendering the given
        `POFileTranslator` objects in the user interface, to reduce the
        number of queries needed while rendering the page.
        """

    def getForPersonPOFile(person, pofile):
        """Retrieve `POFileTranslator` for given `Person` and `POFile`.

        :return: one `POFileTranslator` object matching the requested
            person and pofile, or None.
        """

    def getForTemplate(potemplate):
        """Retrieve `POFileTranslator` objects associated iwth `POTemplate`.

        :param potemplate: `POTemplate` to look for.
        :return: Result set of `POFileTranslator` records associated with
            `POFile`s that translate `potemplate`.
        """
