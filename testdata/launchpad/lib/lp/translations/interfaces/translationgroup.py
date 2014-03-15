# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for groups of translators."""

__metaclass__ = type

__all__ = [
    'ITranslationGroup',
    'ITranslationGroupSet',
    'TranslationPermission',
    ]

from lazr.restful.declarations import (
    collection_default_content,
    export_as_webservice_collection,
    export_as_webservice_entry,
    export_read_operation,
    exported,
    operation_for_version,
    operation_parameters,
    operation_returns_entry,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Datetime,
    Int,
    TextLine,
    )

from lp import _
from lp.app.validators.name import name_validator
from lp.registry.interfaces.role import IHasOwner
from lp.services.fields import (
    PublicPersonChoice,
    Summary,
    Title,
    URIField,
    )
from lp.translations.enums import TranslationPermission


class ITranslationGroup(IHasOwner):
    """A TranslationGroup."""

    export_as_webservice_entry(
        singular_name='translation_group', plural_name='translation_groups')

    id = Int(
            title=_('Translation Group ID'), required=True, readonly=True,
            )
    name = exported(
        TextLine(
            title=_('Name'), required=True,
            description=_("""Keep this name very short, unique, and
            descriptive, because it will be used in URLs. Examples:
            gnome-translation-project, ubuntu-translators."""),
            constraint=name_validator),
        as_of="devel"
        )
    title = exported(
        Title(
            title=_('Title'), required=True,
            description=_("""Title of this Translation Group.
            This title is displayed at the top of the Translation Group
            page and in lists or reports of translation groups.  Do not
            add "translation group" to this title, or it will be shown
            double.
            """),),
        as_of="devel"
        )
    summary = Summary(
            title=_('Summary'), required=True,
            description=_("""A single-paragraph description of the
            group. This will also be displayed in most
            translation group listings."""),
            )
    datecreated = Datetime(
            title=_('Date Created'), required=True, readonly=True,
            )
    owner = PublicPersonChoice(
            title=_('Owner'), required=True, vocabulary='ValidOwner',
            description=_("The owner's IPerson"))
    # joins
    translators = Attribute('The set of translators for this group.')
    projects = Attribute('The projects for which this group translates.')
    products = Attribute('The projects to which this group is directly '
        'appointed as a translator. There may be other projects that are '
        'part of project groups for which the group also translates.')
    distributions = Attribute('The distros for which this group translates.')

    translation_guide_url = URIField(
        title=_('Translation instructions'), required=False,
        allowed_schemes=['http', 'https', 'ftp'],
        allow_userinfo=False,
        description=_("The URL of the generic translation instructions "
                      "followed by this particular translation group. "
                      "This should include team policies and "
                      "recommendations, specific instructions for "
                      "any non-standard behaviour and other documentation."
                      "Can be any of http://, https://, or ftp://."))

    # accessing the translator list
    def query_translator(language):
        """Retrieve a translator, or None, based on a Language"""

    # adding and removing translators
    def remove_translator(language):
        """Remove the translator for this language from the group."""

    # used for the form machinery
    def add(content):
        """Add a new object."""

    top_projects = Attribute(
        "Most relevant projects using this translation group.")

    number_of_remaining_projects = Attribute(
        "Count of remaining projects not listed in the `top_projects`.")

    def __getitem__(language_code):
        """Retrieve the translator for the given language in this group.

        This is used for navigation through the group.
        """

    def fetchTranslatorData():
        """Fetch translators and related data.

        Prefetches display-related properties.

        :return: A result set of (`Translator`, `Language`, `Person`),
            ordered by language name in English.
        """

    def fetchProjectsForDisplay():
        """Fetch `Product`s using this group, for display purposes.

        Prefetches display-related properties.

        :return: A result set of `Product`, ordered by display name.
        """

    def fetchProjectGroupsForDisplay():
        """Fetch `Project`s using this group, for display purposes.

        Prefetches display-related properties.

        :return: A result set of `Project`, ordered by display name.
        """

    def fetchDistrosForDisplay():
        """Fetch `Distribution`s using this group, for display purposes.

        Prefetches display-related properties.

        :return: A result set of `Distribution`, ordered by display name.
        """


class ITranslationGroupSet(Interface):
    """A container for translation groups."""

    export_as_webservice_collection(ITranslationGroup)

    title = Attribute('Title')

    @operation_parameters(
        name=TextLine(title=_("Name of the translation group"),))
    @operation_returns_entry(ITranslationGroup)
    @export_read_operation()
    @operation_for_version('devel')
    def getByName(name):
        """Get a translation group by name."""

    def __getitem__(name):
        """Get a translation group by name."""

    @collection_default_content()
    def _get():
        """Return a collection of all entries."""

    def __iter__():
        """Iterate through the translation groups in this set."""

    def new(name, title, summary, translation_guide_url, owner):
        """Create a new translation group."""

    def getByPerson(person):
        """Return the translation groups which that person is a member of."""

    def getGroupsCount():
        """Return the amount of translation groups available."""
