# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Internal Codehosting API interfaces."""

__metaclass__ = type
__all__ = [
    'BRANCH_ALIAS_PREFIX',
    'branch_id_alias',
    'BRANCH_ID_ALIAS_PREFIX',
    'BRANCH_TRANSPORT',
    'compose_public_url',
    'CONTROL_TRANSPORT',
    'IBazaarApplication',
    'ICodehostingAPI',
    'ICodehostingApplication',
    'LAUNCHPAD_ANONYMOUS',
    'LAUNCHPAD_SERVICES',
    'READ_ONLY',
    'SUPPORTED_SCHEMES',
    'WRITABLE',
    ]

import os.path
import urllib

from lazr.uri import URI
from zope.interface import Interface

from lp.app.validators.name import valid_name
from lp.services.config import config
from lp.services.webapp.interfaces import ILaunchpadApplication

# When LAUNCHPAD_SERVICES is provided as a login ID to XML-RPC methods, they
# bypass the normal security checks and give read-only access to all branches.
# This allows Launchpad services like the puller and branch scanner to access
# private branches.
LAUNCHPAD_SERVICES = '+launchpad-services'
assert not valid_name(LAUNCHPAD_SERVICES), (
    "%r should *not* be a valid name." % (LAUNCHPAD_SERVICES,))

# When LAUNCHPAD_ANONYMOUS is passed, the XML-RPC methods behave as if no user
# was logged in.
LAUNCHPAD_ANONYMOUS = '+launchpad-anonymous'
assert not valid_name(LAUNCHPAD_ANONYMOUS), (
    "%r should *not* be a valid name." % (LAUNCHPAD_ANONYMOUS,))

# These are used as permissions for getBranchInformation.
READ_ONLY = 'r'
WRITABLE = 'w'

# Indicates that a path's real location is on a branch transport.
BRANCH_TRANSPORT = 'BRANCH_TRANSPORT'
# Indicates that a path points to a control directory.
CONTROL_TRANSPORT = 'CONTROL_TRANSPORT'

# The path prefix for getting at branches via their short name.
BRANCH_ALIAS_PREFIX = '+branch'
# The path prefix for getting at branches via their id.
BRANCH_ID_ALIAS_PREFIX = '+branch-id'


def branch_id_alias(branch):
    """Return the path using the branch id alias."""
    return '/%s/%s' % (BRANCH_ID_ALIAS_PREFIX, branch.id)


# The scheme types that are supported for codehosting.
SUPPORTED_SCHEMES = 'bzr+ssh', 'http'


class IBazaarApplication(ILaunchpadApplication):
    """Bazaar Application"""


class ICodehostingApplication(ILaunchpadApplication):
    """Branch Puller application root."""


class ICodehostingAPI(Interface):
    """The codehosting XML-RPC interface to Launchpad.

    Published at 'codehosting' on the private XML-RPC server.

    The code hosting service and puller use this to register branches, to
    retrieve information about a user's branches, and to update their status.
    """

    def acquireBranchToPull(branch_type_names):
        """Return a Branch to pull and mark it as mirror-started.

        :param branch_type_names: Only consider branches of these type names.
            An empty list means consider HOSTED, MIRRORED and IMPORTED
            branches.
        :return: A 5-tuple::

              (branch_id, pull_url, unique_name, default_branch, branch_type)

            where:

              * branch_id is the database id of the branch,
              * pull_url is where to pull from,
              * unique_name is the unique_name of the branch,
              * default_branch is the unique name of the default stacked on
                branch for the branch's target (or '' if there is no such
                branch), and
              * branch_type is one of 'hosted', 'mirrored', or 'imported'.

            or (), the empty tuple, if there is no branch to pull.
        """

    def mirrorFailed(branchID, reason):
        """Notify Launchpad that the branch could not be mirrored.

        The mirror_failures counter for the given branch record will be
        incremented and the next_mirror_time will be set to NULL.

        :param branchID: The database ID of the given branch.
        :param reason: A string giving the reason for the failure.
        :returns: True if the branch status was successfully updated.
            `NoBranchWithID` fault if there's no branch with the given id.
        """

    def recordSuccess(name, hostname, date_started, date_completed):
        """Notify Launchpad that a mirror script has successfully completed.

        Create an entry in the ScriptActivity table with the provided data.

        :param name: Name of the script.
        :param hostname: Where the script was running.

        :param date_started: When the script started, as an UTC time tuple.
        :param date_completed: When the script completed (now), as an UTC time
            tuple.
        :returns: True if the ScriptActivity record was successfully inserted.
        """

    def createBranch(login_id, branch_path):
        """Register a new hosted branch in Launchpad.

        This is called by the bazaar.launchpad.net server when a user
        pushes a new branch to it.  See also
        https://launchpad.canonical.com/SupermirrorFilesystemHierarchy.

        :param login_id: the person ID of the user creating the branch.
        :param branch_path: the path of the branch to be created. This should
            be a URL-escaped string representing an absolute path.
        :returns: the ID for the new branch or a Fault if the branch cannot be
            created.
        """

    def requestMirror(loginID, branchID):
        """Mark a branch as needing to be mirrored.

        :param loginID: the person ID of the user requesting the mirror.
        :param branchID: a branch ID.
        """

    def branchChanged(login_id, branch_id, stacked_on_url, last_revision_id,
                      control_string, branch_string, repository_string):
        """Record that a branch has been changed.

        See `IBranch.branchChanged`.

        :param login_id: the person ID of the user changing the branch.
        :param branch_id: The database id of the branch to operate on.
        :param stacked_on_url: The unique name of the branch this branch is
            stacked on, or '' if this branch is not stacked.
        :param last_revision_id: The tip revision ID of the branch.
        :param control_string: The format string of the control directory of
            the branch.
        :param branch_string: The format string of the branch.
        :param repository_string: The format string of the branch's
            repository.
        """

    def translatePath(requester_id, path):
        """Translate 'path' so that the codehosting transport can access it.

        :param requester_id: the database ID of the person requesting the
            path translation.
        :param path: the path being translated. This should be a URL escaped
            string representing an absolute path.

        :raise `PathTranslationError`: if 'path' cannot be translated.
        :raise `InvalidPath`: if 'path' is known to be invalid.
        :raise `PermissionDenied`: if the requester cannot see the branch.

        :returns: (transport_type, transport_parameters, path_in_transport)
            where 'transport_type' is one of BRANCH_TRANSPORT or
            CONTROL_TRANSPORT, 'transport_parameters' is a dict of data that
            the client can use to construct the transport and
            'path_in_transport' is a path relative to that transport. e.g.
            (BRANCH_TRANSPORT, {'id': 3, 'writable': False}, '.bzr/README').
        """


def compose_public_url(scheme, unique_name, suffix=None):
    # Accept sftp as a legacy protocol.
    accepted_schemes = set(SUPPORTED_SCHEMES)
    accepted_schemes.add('sftp')
    assert scheme in accepted_schemes, "Unknown scheme: %s" % scheme
    host = URI(config.codehosting.supermirror_root).host
    if isinstance(unique_name, unicode):
        unique_name = unique_name.encode('utf-8')
    # After quoting and encoding, the path should be perfectly
    # safe as a plain ASCII string, str() just enforces this
    path = '/' + str(urllib.quote(unique_name, safe='/~+'))
    if suffix:
        path = os.path.join(path, suffix)
    return str(URI(scheme=scheme, host=host, path=path))
