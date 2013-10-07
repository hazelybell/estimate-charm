# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementations of the XML-RPC APIs for codehosting."""

__metaclass__ = type
__all__ = [
    'CodehostingAPI',
    'datetime_from_tuple',
    ]


import datetime

from bzrlib.urlutils import (
    escape,
    unescape,
    )
import pytz
import transaction
from zope.component import getUtility
from zope.interface import implements
from zope.security.interfaces import Unauthorized
from zope.security.management import endInteraction
from zope.security.proxy import removeSecurityProxy

from lp.app.errors import (
    NameLookupFailed,
    NotFoundError,
    )
from lp.app.validators import LaunchpadValidationError
from lp.code.enums import BranchType
from lp.code.errors import (
    BranchCreationException,
    InvalidNamespace,
    UnknownBranchTypeError,
    )
from lp.code.interfaces import branchpuller
from lp.code.interfaces.branch import get_db_branch_info
from lp.code.interfaces.branchlookup import (
    get_first_path_result,
    IBranchLookup,
    ILinkedBranchTraverser,
    )
from lp.code.interfaces.branchnamespace import (
    lookup_branch_namespace,
    split_unique_name,
    )
from lp.code.interfaces.branchtarget import IBranchTarget
from lp.code.interfaces.codehosting import (
    BRANCH_ALIAS_PREFIX,
    branch_id_alias,
    BRANCH_TRANSPORT,
    CONTROL_TRANSPORT,
    ICodehostingAPI,
    LAUNCHPAD_ANONYMOUS,
    LAUNCHPAD_SERVICES,
    )
from lp.code.interfaces.linkedbranch import ICanHasLinkedBranch
from lp.registry.errors import (
    InvalidName,
    NoSuchSourcePackageName,
    )
from lp.registry.interfaces.person import (
    IPersonSet,
    NoSuchPerson,
    )
from lp.registry.interfaces.product import (
    InvalidProductName,
    NoSuchProduct,
    )
from lp.registry.interfaces.sourcepackagename import ISourcePackageNameSet
from lp.services.scripts.interfaces.scriptactivity import IScriptActivitySet
from lp.services.webapp import LaunchpadXMLRPCView
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.interaction import setupInteractionForPerson
from lp.xmlrpc import faults
from lp.xmlrpc.helpers import return_fault


UTC = pytz.timezone('UTC')


def datetime_from_tuple(time_tuple):
    """Create a datetime from a sequence that quacks like time.struct_time.

    The tm_isdst is (index 8) is ignored. The created datetime uses
    tzinfo=UTC.
    """
    [year, month, day, hour, minute, second, unused, unused, unused] = (
        time_tuple)
    return datetime.datetime(
        year, month, day, hour, minute, second, tzinfo=UTC)


def run_with_login(login_id, function, *args, **kwargs):
    """Run 'function' logged in with 'login_id'.

    The first argument passed to 'function' will be the Launchpad
    `Person` object corresponding to 'login_id'.

    The exception is when the requesting login ID is `LAUNCHPAD_SERVICES`. In
    that case, we'll pass through the `LAUNCHPAD_SERVICES` variable and the
    method will do whatever security proxy hackery is required to provide read
    privileges to the Launchpad services.
    """
    if login_id == LAUNCHPAD_SERVICES or login_id == LAUNCHPAD_ANONYMOUS:
        # Don't pass in an actual user. Instead pass in LAUNCHPAD_SERVICES
        # and expect `function` to use `removeSecurityProxy` or similar.
        return function(login_id, *args, **kwargs)
    if isinstance(login_id, basestring):
        requester = getUtility(IPersonSet).getByName(login_id)
    else:
        requester = getUtility(IPersonSet).get(login_id)
    if requester is None:
        raise NotFoundError("No person with id %s." % login_id)
    setupInteractionForPerson(requester)
    try:
        return function(requester, *args, **kwargs)
    finally:
        endInteraction()


class CodehostingAPI(LaunchpadXMLRPCView):
    """See `ICodehostingAPI`."""

    implements(ICodehostingAPI)

    def acquireBranchToPull(self, branch_type_names):
        """See `ICodehostingAPI`."""
        branch_types = []
        for branch_type_name in branch_type_names:
            try:
                branch_types.append(BranchType.items[branch_type_name])
            except KeyError:
                raise UnknownBranchTypeError(
                    'Unknown branch type: %r' % (branch_type_name,))
        branch = getUtility(branchpuller.IBranchPuller).acquireBranchToPull(
            *branch_types)
        if branch is not None:
            branch = removeSecurityProxy(branch)
            default_branch = branch.target.default_stacked_on_branch
            if default_branch is None:
                default_branch_name = ''
            elif (branch.branch_type == BranchType.MIRRORED
                  and default_branch.private):
                default_branch_name = ''
            else:
                default_branch_name = '/' + default_branch.unique_name
            return (branch.id, branch.getPullURL(), branch.unique_name,
                    default_branch_name, branch.branch_type.name)
        else:
            return ()

    def mirrorFailed(self, branch_id, reason):
        """See `ICodehostingAPI`."""
        branch = getUtility(IBranchLookup).get(branch_id)
        if branch is None:
            return faults.NoBranchWithID(branch_id)
        # The puller runs as no user and may pull private branches. We need to
        # bypass Zope's security proxy to set the mirroring information.
        removeSecurityProxy(branch).mirrorFailed(reason)
        return True

    def recordSuccess(self, name, hostname, started_tuple, completed_tuple):
        """See `ICodehostingAPI`."""
        date_started = datetime_from_tuple(started_tuple)
        date_completed = datetime_from_tuple(completed_tuple)
        getUtility(IScriptActivitySet).recordSuccess(
            name=name, date_started=date_started,
            date_completed=date_completed, hostname=hostname)
        return True

    def _getBranchNamespaceExtras(self, path, requester):
        """Get the branch namespace, branch name and callback for the path.

        If the path defines a full branch path including the owner and branch
        name, then the namespace that is returned is the namespace for the
        owner and the branch target specified.

        If the path uses an lp short name, then we only allow the requester to
        create a branch if they have permission to link the newly created
        branch to the short name target.  If there is an existing branch
        already linked, then BranchExists is raised.  The branch name that is
        used is determined by the namespace as the first unused name starting
        with 'trunk'.
        """
        if path.startswith(BRANCH_ALIAS_PREFIX + '/'):
            path = path[len(BRANCH_ALIAS_PREFIX) + 1:]
            if not path.startswith('~'):
                context = getUtility(ILinkedBranchTraverser).traverse(path)
                target = IBranchTarget(context)
                namespace = target.getNamespace(requester)
                branch_name = namespace.findUnusedName('trunk')

                def link_func(new_branch):
                    link = ICanHasLinkedBranch(context)
                    link.setBranch(new_branch, requester)
                return namespace, branch_name, link_func, path
        namespace_name, branch_name = split_unique_name(path)
        namespace = lookup_branch_namespace(namespace_name)
        return namespace, branch_name, None, path

    def createBranch(self, login_id, branch_path):
        """See `ICodehostingAPI`."""
        def create_branch(requester):
            if not branch_path.startswith('/'):
                return faults.InvalidPath(branch_path)
            escaped_path = unescape(branch_path.strip('/'))
            try:
                namespace, branch_name, link_func, path = (
                    self._getBranchNamespaceExtras(escaped_path, requester))
            except ValueError:
                return faults.PermissionDenied(
                    "Cannot create branch at '%s'" % branch_path)
            except InvalidNamespace:
                return faults.PermissionDenied(
                    "Cannot create branch at '%s'" % branch_path)
            except NoSuchPerson as e:
                return faults.NotFound(
                    "User/team '%s' does not exist." % e.name)
            except NoSuchProduct as e:
                return faults.NotFound(
                    "Project '%s' does not exist." % e.name)
            except InvalidProductName as e:
                return faults.InvalidProductName(escape(e.name))
            except NoSuchSourcePackageName as e:
                try:
                    getUtility(ISourcePackageNameSet).new(e.name)
                except InvalidName:
                    return faults.InvalidSourcePackageName(e.name)
                return self.createBranch(login_id, branch_path)
            except NameLookupFailed as e:
                return faults.NotFound(str(e))
            try:
                branch = namespace.createBranch(
                    BranchType.HOSTED, branch_name, requester)
            except LaunchpadValidationError as e:
                msg = e.args[0]
                if isinstance(msg, unicode):
                    msg = msg.encode('utf-8')
                return faults.PermissionDenied(msg)
            except BranchCreationException as e:
                return faults.PermissionDenied(str(e))

            if link_func:
                try:
                    link_func(branch)
                except Unauthorized:
                    # We don't want to keep the branch we created.
                    transaction.abort()
                    return faults.PermissionDenied(
                        "Cannot create linked branch at '%s'." % path)

            return branch.id
        return run_with_login(login_id, create_branch)

    def _canWriteToBranch(self, requester, branch):
        """Can `requester` write to `branch`?"""
        if requester == LAUNCHPAD_SERVICES:
            return False
        return (branch.branch_type == BranchType.HOSTED
                and check_permission('launchpad.Edit', branch))

    def requestMirror(self, login_id, branchID):
        """See `ICodehostingAPI`."""
        def request_mirror(requester):
            branch = getUtility(IBranchLookup).get(branchID)
            # We don't really care who requests a mirror of a branch.
            branch.requestMirror()
            return True
        return run_with_login(login_id, request_mirror)

    def branchChanged(self, login_id, branch_id, stacked_on_location,
                      last_revision_id, control_string, branch_string,
                      repository_string):
        """See `ICodehostingAPI`."""
        def branch_changed(requester):
            branch_set = getUtility(IBranchLookup)
            branch = branch_set.get(branch_id)
            if branch is None:
                return faults.NoBranchWithID(branch_id)

            if requester == LAUNCHPAD_SERVICES:
                branch = removeSecurityProxy(branch)

            info = get_db_branch_info(
                stacked_on_location, last_revision_id, control_string,
                branch_string, repository_string)
            branch.branchChanged(**info)

            return True

        return run_with_login(login_id, branch_changed)

    def _serializeBranch(self, requester, branch, trailing_path,
                         force_readonly=False):
        if requester == LAUNCHPAD_SERVICES:
            branch = removeSecurityProxy(branch)
        try:
            branch_id = branch.id
        except Unauthorized:
            raise faults.PermissionDenied()
        if branch.branch_type == BranchType.REMOTE:
            return None
        if force_readonly:
            writable = False
        else:
            writable = self._canWriteToBranch(requester, branch)
        return (
            BRANCH_TRANSPORT,
            {'id': branch_id, 'writable': writable},
            trailing_path)

    def _serializeControlDirectory(self, requester, lookup):
        try:
            namespace = lookup_branch_namespace(lookup['control_name'])
        except (InvalidNamespace, NotFoundError):
            return
        trailing_path = lookup['trailing'].lstrip('/')
        if not ('.bzr' == trailing_path or trailing_path.startswith('.bzr/')):
            # '.bzr' is OK, '.bzr/foo' is OK, '.bzrfoo' is not.
            return
        default_branch = namespace.target.default_stacked_on_branch
        if default_branch is None:
            return
        try:
            path = branch_id_alias(default_branch)
        except Unauthorized:
            return
        return (
            CONTROL_TRANSPORT,
            {'default_stack_on': escape(path)},
            escape(trailing_path))

    def performLookup(self, requester, path, lookup):
        looker = getUtility(IBranchLookup)
        if lookup['type'] == 'control_name':
            return self._serializeControlDirectory(requester, lookup)
        branch, trailing = looker.performLookup(lookup)
        if branch is None:
            return None
        trailing = trailing.lstrip('/')
        serialized = self._serializeBranch(requester, branch, trailing,
                                           lookup['type'] == 'id')
        if serialized is None:
            raise faults.PathTranslationError(path)
        return serialized

    def translatePath(self, requester_id, path):
        """See `ICodehostingAPI`."""
        @return_fault
        def translate_path(requester):
            if not path.startswith('/'):
                return faults.InvalidPath(path)
            stripped_path = unescape(path.strip('/'))
            lookup = lambda l: self.performLookup(requester_id, path, l)
            result = get_first_path_result(stripped_path, lookup, None)
            if result is None:
                raise faults.PathTranslationError(path)
            return result
        return run_with_login(requester_id, translate_path)
