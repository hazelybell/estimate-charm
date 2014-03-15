# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for pillar and artifact access policies."""

__metaclass__ = type

__all__ = [
    'IAccessArtifact',
    'IAccessArtifactGrant',
    'IAccessArtifactGrantSource',
    'IAccessArtifactSource',
    'IAccessPolicy',
    'IAccessPolicyArtifact',
    'IAccessPolicyArtifactSource',
    'IAccessPolicyGrant',
    'IAccessPolicyGrantFlatSource',
    'IAccessPolicyGrantSource',
    'IAccessPolicySource',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )


class IAccessArtifact(Interface):
    """An artifact that has its own access control rules.

    Examples are a bug or a branch.
    """

    id = Attribute("ID")
    concrete_artifact = Attribute("Concrete artifact")
    bug_id = Attribute("bug_id")
    branch_id = Attribute("branch_id")
    specification_id = Attribute("specification_id")


class IAccessArtifactGrant(Interface):
    """A grant for a person or team to access an artifact.

    For example, the reporter of an private security bug has a grant for
    that bug.
    """

    grantee = Attribute("Grantee")
    grantor = Attribute("Grantor")
    date_created = Attribute("Date created")
    abstract_artifact = Attribute("Abstract artifact")

    concrete_artifact = Attribute("Concrete artifact")


class IAccessPolicy(Interface):
    """A policy to govern access to a category of a project's artifacts.

    An example is Ubuntu security, which controls access to Ubuntu's embargoed
    security bugs.
    """

    id = Attribute("ID")
    pillar = Attribute("Pillar")
    type = Attribute("Type")
    person = Attribute("Person")


class IAccessPolicyArtifact(Interface):
    """An association between an artifact and a policy.

    For example, a security bug in Ubuntu is associated with the Ubuntu
    security policy so people with a grant for that policy can see it.
    """

    abstract_artifact = Attribute("Abstract artifact")
    policy = Attribute("Access policy")


class IAccessPolicyGrant(Interface):
    """A grant for a person or team to access all of a policy's artifacts.

    For example, the Canonical security team has a grant for Ubuntu's
    security policy so they can see private security bugs.
    """

    grantee = Attribute("Grantee")
    grantor = Attribute("Grantor")
    date_created = Attribute("Date created")
    policy = Attribute("Access policy")


class IAccessArtifactSource(Interface):

    def ensure(concrete_artifacts):
        """Return `IAccessArtifact`s for the concrete artifacts.

        Creates abstract artifacts if they don't already exist.
        """

    def find(concrete_artifacts):
        """Return the `IAccessArtifact`s for the artifacts, if they exist.

        Use ensure() if you want to create them if they don't yet exist.
        """

    def delete(concrete_artifacts):
        """Delete the `IAccessArtifact`s for the concrete artifact.

        Also revokes any `IAccessArtifactGrant`s for the artifacts.
        """


class IAccessArtifactGrantSource(Interface):

    def grant(grants):
        """Create `IAccessArtifactGrant`s.

        :param grants: a collection of
            (`IAccessArtifact`, grantee `IPerson`, grantor `IPerson`) triples
            to grant.
        """

    def find(grants):
        """Return the specified `IAccessArtifactGrant`s if they exist.

        :param grants: a collection of (`IAccessArtifact`, grantee `IPerson`)
            pairs.
        """

    def findByArtifact(artifacts, grantees=None):
        """Return `IAccessArtifactGrant` objects for the artifacts.

        :param artifacts: the artifacts for which to find any grants.
        :param grantees: find grants for the specified grantees only,
            else find all grants.
        """

    def revokeByArtifact(artifacts, grantees=None):
        """Delete `IAccessArtifactGrant` objects for the artifacts.

        :param artifacts: the artifacts to which revoke access.
        :param grantees: revoke access for the specified grantees only,
            else delete all grants.
        """


class IAccessPolicyArtifactSource(Interface):

    def create(links):
        """Create `IAccessPolicyArtifacts`s.

        :param links: a collection of (`IAccessArtifact`, `IAccessPolicy`)
            pairs to link.
        """

    def find(links):
        """Return the specified `IAccessPolicyArtifacts`s if they exist.

        :param links: a collection of (`IAccessArtifact`, `IAccessPolicy`)
            pairs.
        """

    def delete(links):
        """Delete the specified `IAccessPolicyArtifacts`s.

        :param links: a collection of (`IAccessArtifact`, `IAccessPolicy`)
            pairs.
        """

    def findByArtifact(artifacts):
        """Return all `IAccessPolicyArtifact` objects for the artifacts."""

    def findByPolicy(policies):
        """Return all `IAccessPolicyArtifact` objects for the policies."""

    def deleteByArtifact(artifacts):
        """Delete all `IAccesyPolicyArtifact` objects for the artifacts."""


class IAccessPolicySource(Interface):

    def create(pillars_and_types):
        """Create an `IAccessPolicy` for the given pillars and types.

        :param pillars_and_types: a collection of
            (`IProduct` or `IDistribution`, `InformationType`) pairs to
            create `IAccessPolicy` objects for.
        :return: a collection of the created `IAccessPolicy` objects.
        """

    def createForTeams(teams):
        """Create an `IAccessPolicy` for the given teams.

        :param teams: a collection of teams to create `IAccessPolicy`
            objects for.
        :return: a collection of the created `IAccessPolicy` objects.
        """

    def find(pillars_and_types):
        """Return the `IAccessPolicy`s for the given pillars and types.

        :param pillars_and_types: a collection of
            (`IProduct` or `IDistribution`, `InformationType`) pairs to
            find.
        """

    def findByID(ids):
        """Return the `IAccessPolicy`s with the given IDs."""

    def findByPillar(pillars):
        """Return a `ResultSet` of all `IAccessPolicy`s for the pillars."""

    def findByTeam(teams):
        """Return a `ResultSet` of all `IAccessPolicy`s for the teams."""

    def delete(pillars_and_types):
        """Delete the given pillars and types.

        :param pillars_and_types: a collection of
            (`IProduct` or `IDistribution`, `InformationType`) pairs delete.
        """


class IAccessPolicyGrantSource(Interface):

    def grant(grants):
        """Create `IAccessPolicyGrant`s.

        :param grants: a collection of
            (`IAccessPolicy`, grantee `IPerson`, grantor `IPerson`) triples
            to grant.
        """

    def find(grants):
        """Return the specified `IAccessPolicyGrant`s if they exist.

        :param grants: a collection of (`IAccessPolicy`, grantee `IPerson`)
            pairs.
        """

    def findByPolicy(policies):
        """Return all `IAccessPolicyGrant` objects for the policies."""

    def revoke(grants):
        """Revoke the specified grants.

        :param grants: a collection of (`IAccessPolicy`, grantee `IPerson`)
            pairs.
        """

    def revokeByPolicy(policies):
        """Revoke all `IAccessPolicyGrant` for the policies."""


class IAccessPolicyGrantFlatSource(Interface):
    """Experimental query utility to search through the flattened schema."""

    def findGranteesByPolicy(policies):
        """Find teams or users with access grants for the policies.

        This includes grants for artifacts in the policies.

        :param policies: a collection of `IAccesPolicy`s.
        :return: a collection of `IPerson`.
        """

    def findGranteePermissionsByPolicy(policies, grantees=None):
        """Find teams or users with access grants for the policies.

        This includes grants for artifacts in the policies.

        :param policies: a collection of `IAccesPolicy`s.
        :param grantees: if not None, the result only includes people in the
            specified list of grantees.
        :return: a collection of
            (`IPerson`, `IAccessPolicy`, permission, shared_artifact_types)
            where permission is a SharingPermission enum value.
            ALL means the person has an access policy grant and can see all
            artifacts for the associated pillar.
            SOME means the person only has specified access artifact grants.
            shared_artifact_types contains the information_types for which the
            user has been granted access for one or more artifacts of that
            type.
        """

    def findArtifactsByGrantee(grantee, policies):
        """Find the `IAccessArtifact`s for grantee and policies.

        :param grantee: the access artifact grantee.
        :param policies: a collection of `IAccessPolicy`s.
        """
