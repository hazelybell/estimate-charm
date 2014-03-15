# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces that define common roles associated with objects."""

__metaclass__ = type

__all__ = [
    'IHasAppointedDriver',
    'IHasDrivers',
    'IHasOwner',
    'IPersonRoles',
    ]


from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    )

from lp import _


class IHasOwner(Interface):
    """An object that has an owner."""

    owner = Attribute("The object's owner, which is an IPerson.")


class IHasDrivers(Interface):
    """An object that has drivers.

    Drivers have permission to approve bugs and features for specific
    series.
    """
    drivers = Attribute("A list of drivers")

    def personHasDriverRights(person):
        """Does the given person have launchpad.Driver rights on this object?

        True if the person is one of this object's drivers, its owner or a
        Launchpad admin.
        """


class IHasAppointedDriver(Interface):
    """An object that has an appointed driver."""

    driver = Choice(
        title=_("Driver"), required=False, vocabulary='ValidPersonOrTeam')


class IPersonRoles(Interface):
    """What celebrity teams a person is member of and similar helpers.

    Convenience methods that remove frequent calls to ILaunchpadCelebrities
    and IPerson.inTeam from permission checkers. May also be used in model
    or view code.

    All person celebrities in ILaunchpadCelbrities must have a matching
    in_ attribute here and vice versa.
    """

    person = Attribute("The IPerson object that these checks refer to.")

    in_admin = Bool(
        title=_("True if this person is a Launchpad admin."),
        required=True, readonly=True)
    in_software_center_agent = Bool(
        title=_("True if this person is the Software Center Agent."),
        required=True, readonly=True)
    in_bug_importer = Bool(
        title=_("True if this person is a bug importer."),
        required=True, readonly=True)
    in_bug_watch_updater = Bool(
        title=_("True if this person is a bug watch updater."),
        required=True, readonly=True)
    in_buildd_admin = Bool(
        title=_("True if this person is a buildd admin."),
        required=True, readonly=True)
    in_commercial_admin = Bool(
        title=_("True if this person is a commercial admin."),
        required=True, readonly=True)
    in_hwdb_team = Bool(
        title=_("True if this person is on the hwdb team."),
        required=True, readonly=True)
    in_janitor = Bool(
        title=_("True if this person is the janitor."),
        required=True, readonly=True)
    in_katie = Bool(
        title=_("True if this person is Katie."),
        required=True, readonly=True)
    in_launchpad_developers = Bool(
        title=_("True if this person is a Launchpad developer."),
        required=True, readonly=True)
    in_ppa_key_guard = Bool(
        title=_("True if this person is the ppa key guard."),
        required=True, readonly=True)
    in_ppa_self_admins = Bool(
        title=_("True if this person is a PPA self admin."),
        required=True, readonly=True)
    in_registry_experts = Bool(
        title=_("True if this person is a registry expert."),
        required=True, readonly=True)
    in_rosetta_experts = Bool(
        title=_("True if this person is a rosetta expert."),
        required=True, readonly=True)
    in_ubuntu_techboard = Bool(
        title=_("True if this person is on the Ubuntu tech board."),
        required=True, readonly=True)
    in_vcs_imports = Bool(
        title=_("True if this person is on the vcs-imports team."),
        required=True, readonly=True)

    def inTeam(team):
        """Is this person a member or the owner of `team`?

        Passed through to the *unproxied* same method in
        `IPersonViewRestricted`.
        """

    def isOwner(obj):
        """Is this person the owner of the object?"""

    def isDriver(obj):
        """Is this person the driver of the object?"""

    def isBugSupervisor(obj):
        """Is this person the bug supervisor of the object?"""

    def isOneOfDrivers(obj):
        """Is this person on of the drivers of the object?

        Works on objects that implement 'IHasDrivers' but will default to
        isDriver if it doesn't, i.e. check the driver attribute.
        """

    def isOneOf(obj, attributes):
        """Is this person one of the roles in relation to the object?

        Check if the person is inTeam of one of the given IPerson attributes
        of the object.

        :param obj: The object to check the relation to.
        :param attributes: A list of attribute names to check with inTeam.
        """
