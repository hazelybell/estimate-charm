# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'ITranslationsPerson',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import Bool

from lp import _


class ITranslationsPerson(Interface):
    """Translation-related properties of a person."""

    translatable_languages = Attribute(
        _('Languages this person knows, apart from English'))

    translation_history = Attribute(
        "The set of POFileTranslator objects that represent work done "
        "by this translator.")

    translation_groups = Attribute(
        "The set of TranslationGroup objects this person is a member of.")

    translators = Attribute(
        "The set of Translator objects this person is a member of.")

    translations_relicensing_agreement = Bool(
        title=_("Whether person agrees to relicense their translations"),
        readonly=False)

    def getTranslationHistory(no_older_than=None):
        """Query most recent `POFileTranslator` entries for this person.

        :param no_older_than: Optional cutoff date.  If given, older
            `POFileTranslator` entries are ignored.
        :return: a Storm query result.
        """

    def hasTranslated():
        """Has this user done any translation work?"""

    def getReviewableTranslationFiles(no_older_than=None):
        """List `POFile`s this person should be able to review.

        These are translations that this person has worked on in the
        (relatively recent) past and is a reviewer for.

        :param no_older_than: Optional cutoff date.  Translations that
            this person hasn't contributed to since this date will be
            ignored.
        :return: A query result of `POFile`s ordered by age of oldest
            unreviewed `TranslationMessage` (oldest first).
        """

    def getTranslatableFiles(no_older_than=None, urgent_first=True):
        """List `POFile`s this person should be able to help translate.

        These are translations that this person is not a reviewer for,
        but has worked on recently.

        :param no_older_than: Optional cutoff date to define "recently."
        :param urgent_first: If True, sort `POFile`s with the most
            untranslated strings to the front.  If False, sort the other
            way around.
        :return: A query result of `POFile`s ordered by number of
            untranslated messages.
        """
