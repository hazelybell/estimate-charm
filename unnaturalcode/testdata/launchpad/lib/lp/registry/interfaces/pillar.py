# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Launchpad Pillars share a namespace.

Pillars are currently Product, ProjectGroup and Distribution.
"""

__metaclass__ = type

from lazr.restful.declarations import (
    export_as_webservice_entry,
    export_read_operation,
    exported,
    operation_parameters,
    operation_returns_collection_of,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Int,
    List,
    TextLine,
    )

from lp import _
from lp.registry.enums import (
    BranchSharingPolicy,
    BugSharingPolicy,
    SpecificationSharingPolicy,
    )


__all__ = [
    'IHasAliases',
    'IHasSharingPolicies',
    'IPillar',
    'IPillarName',
    'IPillarNameSet',
    'IPillarPerson',
    'IPillarPersonFactory',
    ]


class IPillar(Interface):
    """An object that might be a project, a project group, or a distribution.

    This is a polymorphic object served by the pillar set. Check the
    individual object to see what type it is.
    """
    export_as_webservice_entry()
    active = exported(
        Bool(title=_('Active'),
             description=_("Whether or not this item is active.")))
    pillar_category = Attribute('The category title applicable to the pillar')


class IHasAliases(Interface):

    aliases = List(
        title=_('Aliases'), required=False, readonly=True,
        description=_(
            "The names (as strings) which are aliases to this pillar."))

    # Instead of a method for setting aliases we could make the 'aliases'
    # attribute writable, but we decided to go with a method because this
    # operation may trigger several inserts/deletes in the database and a
    # method helps clarifying it may be an expensive operation.
    def setAliases(names):
        """Set the given names as this pillar's aliases.

        For each of the given names, check that it's not already in use by
        another pillar and then make sure it exists as an alias for this
        pillar.  If the given names don't include any of this pillar's
        existing aliases, these are deleted.

        :param names: A sequence of names (as strings) that should be aliases
            to this pillar.
        """


class IHasSharingPolicies(Interface):
    """Sharing policies used to define bug and branch visibility rules."""
    branch_sharing_policy = exported(Choice(
        title=_('Branch sharing policy'),
        description=_("Sharing policy for this pillar's branches."),
        required=False, readonly=True, vocabulary=BranchSharingPolicy),
        as_of='devel')
    bug_sharing_policy = exported(Choice(
        title=_('Bug sharing policy'),
        description=_("Sharing policy for this pillar's bugs."),
        required=False, readonly=True, vocabulary=BugSharingPolicy),
        as_of='devel')
    specification_sharing_policy = exported(Choice(
        title=_('Blueprint sharing policy'),
        description=_("Sharing policy for this project's specifications."),
        required=False, readonly=True, vocabulary=SpecificationSharingPolicy),
        as_of='devel')


class IPillarName(Interface):
    """A data structure for identifying a pillar.

    This includes the pillar object, as well as information about whether
    it's a project, project group, or distribution.
    """
    id = Int(title=_('The PillarName ID'))
    name = TextLine(title=u"The name.")
    product = Attribute('The project that has this name, or None')
    project = Attribute('The project that has this name, or None')
    distribution = Attribute('The distribution that has this name, or None')
    active = Attribute('The pillar is active')
    pillar = Attribute('The pillar object')


class IPillarNameSet(Interface):
    """An object for searching across projects, project groups, and distros.

    Projects, project groups, and distributions are collectively known as
    "pillars". This object lets you do a combined search across all
    types of pillars. It also gives you access to pillars that have
    been flagged by administrators as "featured" pillars.
    """
    export_as_webservice_entry('pillars')

    def __contains__(name):
        """True if the given name is an active Pillar or an alias to one."""

    def __getitem__(name):
        """Get an active pillar by its name or any of its aliases.

        If there's no pillar with the given name or there is one but it's
        inactive, raise NotFoundError.
        """

    def getByName(name, ignore_inactive=False):
        """Return the pillar whose name or alias matches the given name.

        If ignore_inactive is True, then only active pillars are considered.

        If no pillar is found, return None.
        """

    def count_search_matches(text):
        """Return the total number of Pillars matching :text:"""

    @operation_parameters(text=TextLine(title=u"Search text"),
                          limit=Int(title=u"Maximum number of items to "
                                    "return. This is a hard limit: any "
                                    "pagination you request will happen "
                                    "within this limit.",
                                    required=False))
    @operation_returns_collection_of(IPillar)
    @export_read_operation()
    def search(text, limit):
        """Return Projects/Project groups/Distros matching :text:.

        If :limit: is None, the default batch size will be used.

        The results are ordered descending by rank.
        """

    def add_featured_project(project):
        """Add a project to the featured project list."""

    def remove_featured_project(project):
        """Remove a project from the featured project list."""

    featured_projects = exported(
        CollectionField(
            title=_('Projects, project groups, and distributions that are '
                    'featured on the site.'),
            value_type=Reference(schema=IPillar)),
        exported_as="featured_pillars"
        )


class IPillarPerson(Interface):
    """A Person's connection to a Pillar."""

    person = Attribute("The person associated with the pillar.")
    pillar = Attribute("The pillar associated with the person.")


class IPillarPersonFactory(Interface):
    """Creates `IPillarPerson`s."""

    def create(person, pillar):
        """Create and return an `IPillarPerson`."""
