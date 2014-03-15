# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import httplib
import socket
import sys
import urllib2

# FIRST Ensure correct plugins are loaded. Do not delete this comment or the
# line below this comment.
import lp.codehosting

from bzrlib import (
    errors,
    urlutils,
    )
from bzrlib.branch import Branch
from bzrlib.plugins.loom.branch import LoomSupport
from bzrlib.plugins.weave_fmt.branch import BzrBranchFormat4
from bzrlib.plugins.weave_fmt.repository import (
    RepositoryFormat4,
    RepositoryFormat5,
    RepositoryFormat6,
    )
from bzrlib.transport import get_transport
import bzrlib.ui
from bzrlib.ui import SilentUIFactory
from lazr.uri import (
    InvalidURIError,
    URI,
    )

from lp.code.bzr import (
    BranchFormat,
    RepositoryFormat,
    )
from lp.code.enums import BranchType
from lp.codehosting.bzrutils import identical_formats
from lp.codehosting.puller import get_lock_id_for_branch_id
from lp.codehosting.safe_open import (
    BadUrl,
    BranchLoopError,
    BranchOpenPolicy,
    BranchReferenceForbidden,
    SafeBranchOpener,
    )
from lp.services.config import config
from lp.services.webapp import errorlog


__all__ = [
    'BadUrlLaunchpad',
    'BadUrlScheme',
    'BadUrlSsh',
    'BranchMirrorer',
    'BranchMirrorerPolicy',
    'get_canonical_url_for_branch_name',
    'install_worker_ui_factory',
    'PullerWorker',
    'PullerWorkerProtocol',
    ]


class BadUrlSsh(BadUrl):
    """Tried to access a branch from sftp or bzr+ssh."""


class BadUrlLaunchpad(BadUrl):
    """Tried to access a branch from launchpad.net."""


class BadUrlScheme(BadUrl):
    """Found a URL with an untrusted scheme."""

    def __init__(self, scheme, url):
        BadUrl.__init__(self, scheme, url)
        self.scheme = scheme


def get_canonical_url_for_branch_name(unique_name):
    """Custom implementation of canonical_url(branch) for error reporting.

    The actual `canonical_url` function cannot be used because we do not have
    access to real content objects.
    """
    if config.vhosts.use_https:
        scheme = 'https'
    else:
        scheme = 'http'
    hostname = config.vhost.code.hostname
    return scheme + '://' + hostname + '/' + unique_name


class PullerWorkerProtocol:
    """The protocol used to communicate with the puller scheduler.

    This protocol notifies the scheduler of events such as startMirroring,
    branchChanged and mirrorFailed.
    """

    def __init__(self, output):
        self.out_stream = output

    def sendNetstring(self, string):
        self.out_stream.write('%d:%s,' % (len(string), string))

    def sendEvent(self, command, *args):
        self.sendNetstring(command)
        self.sendNetstring(str(len(args)))
        for argument in args:
            self.sendNetstring(str(argument))

    def startMirroring(self):
        self.sendEvent('startMirroring')

    def branchChanged(self, stacked_on_url, revid_before, revid_after,
                      control_string, branch_string, repository_string):
        self.sendEvent(
            'branchChanged', stacked_on_url, revid_before, revid_after,
            control_string, branch_string, repository_string)

    def mirrorFailed(self, message, oops_id):
        self.sendEvent('mirrorFailed', message, oops_id)

    def progressMade(self, type):
        # 'type' is ignored; we only care about the type of progress in the
        # tests of the progress reporting.
        self.sendEvent('progressMade')

    def log(self, fmt, *args):
        self.sendEvent('log', fmt % args)


class BranchMirrorerPolicy(BranchOpenPolicy):
    """The policy for what branches to open and how to stack them."""

    def createDestinationBranch(self, source_branch, destination_url):
        """Create a destination branch for 'source_branch'.

        Creates a branch at 'destination_url' that is has the same format as
        'source_branch'.  Any content already at 'destination_url' will be
        deleted.  Generally the new branch will have no revisions, but they
        will be copied for import branches, because this can be done safely
        and efficiently with a vfs-level copy (see `ImportedBranchPolicy`).

        :param source_branch: The Bazaar branch that will be mirrored.
        :param destination_url: The place to make the destination branch. This
            URL must point to a writable location.
        :return: The destination branch.
        """
        dest_transport = get_transport(destination_url)
        if dest_transport.has('.'):
            dest_transport.delete_tree('.')
        if isinstance(source_branch, LoomSupport):
            # Looms suck.
            revision_id = None
        else:
            revision_id = 'null:'
        source_branch.bzrdir.clone_on_transport(
            dest_transport, revision_id=revision_id)
        return Branch.open(destination_url)

    def getStackedOnURLForDestinationBranch(self, source_branch,
                                            destination_url):
        """Get the stacked on URL for `source_branch`.

        In particular, the URL it should be stacked on when it is mirrored to
        `destination_url`.
        """
        return None


class BranchMirrorer(object):
    """A `BranchMirrorer` safely makes mirrors of branches.

    A `BranchMirrorer` has a `BranchOpenPolicy` to tell it which URLs are safe
    to accesss and whether or not to follow branch references.

    The mirrorer knows how to follow branch references, create new mirrors,
    update existing mirrors, determine stacked-on branches and the like.

    Public methods are `open` and `mirror`.
    """

    def __init__(self, policy, protocol=None, log=None):
        """Construct a branch opener with 'policy'.

        :param policy: A `BranchOpenPolicy` that tells us what URLs are valid
            and similar things.
        :param log: A callable which can be called with a format string and
            arguments to log messages in the scheduler, or None, in which case
            log messages are discarded.
        """
        self.policy = policy
        self.protocol = protocol
        self.opener = SafeBranchOpener(policy)
        if log is not None:
            self.log = log
        else:
            self.log = lambda *args: None

    def createDestinationBranch(self, source_branch, destination_url):
        """Create a destination branch for 'source_branch'.

        Creates a branch at 'destination_url' that is a mirror of
        'source_branch'. Any content already at 'destination_url' will be
        deleted.

        :param source_branch: The Bazaar branch that will be mirrored.
        :param destination_url: The place to make the destination branch. This
            URL must point to a writable location.
        :return: The destination branch.
        """
        return self.opener.runWithTransformFallbackLocationHookInstalled(
            self.policy.createDestinationBranch, source_branch,
            destination_url)

    def openDestinationBranch(self, source_branch, destination_url):
        """Open or create the destination branch at 'destination_url'.

        :param source_branch: The Bazaar branch that will be mirrored.
        :param destination_url: The place to make the destination branch. This
            URL must point to a writable location.
        :return: The opened or created branch.
        """
        try:
            branch = Branch.open(destination_url)
        except (errors.NotBranchError, errors.IncompatibleRepositories):
            # Make a new branch in the same format as the source branch.
            return self.createDestinationBranch(
                source_branch, destination_url)
        # Check that destination branch is in the same format as the source.
        if identical_formats(source_branch, branch):
            return branch
        self.log('Formats differ.')
        return self.createDestinationBranch(source_branch, destination_url)

    def updateBranch(self, source_branch, dest_branch):
        """Bring 'dest_branch' up-to-date with 'source_branch'.

        This method pulls 'source_branch' into 'dest_branch' and sets the
        stacked-on URL of 'dest_branch' to match 'source_branch'.

        This method assumes that 'source_branch' and 'dest_branch' both have
        the same format.
        """
        stacked_on_url = self.policy.getStackedOnURLForDestinationBranch(
            source_branch, dest_branch.base)
        try:
            dest_branch.set_stacked_on_url(stacked_on_url)
        except (errors.UnstackableRepositoryFormat,
                errors.UnstackableBranchFormat,
                errors.IncompatibleRepositories):
            stacked_on_url = None
        if stacked_on_url is None:
            # We use stacked_on_url == '' to mean "no stacked on location"
            # because XML-RPC doesn't support None.
            stacked_on_url = ''
        dest_branch.pull(source_branch, overwrite=True)
        return stacked_on_url

    def mirror(self, source_branch, destination_url):
        """Mirror 'source_branch' to 'destination_url'."""
        branch = self.openDestinationBranch(source_branch, destination_url)
        revid_before = branch.last_revision()
        # If the branch is locked, try to break it. Our special UI factory
        # will allow the breaking of locks that look like they were left
        # over from previous puller worker runs. We will block on other
        # locks and fail if they are not broken before the timeout expires
        # (currently 5 minutes).
        if branch.get_physical_lock_status():
            branch.break_lock()
        stacked_on_url = self.updateBranch(source_branch, branch)
        return branch, revid_before, stacked_on_url

    def open(self, url):
        return self.opener.open(url)


class PullerWorker:
    """This class represents a single branch that needs mirroring.

    It has a source URL, a destination URL, a database id, a unique name and a
    status client which is used to report on the mirror progress.
    """

    def _checkerForBranchType(self, branch_type):
        """Return a `BranchMirrorer` with an appropriate policy.

        :param branch_type: A `BranchType`. The policy of the mirrorer will
            be based on this.
        :return: A `BranchMirrorer`.
        """
        return make_branch_mirrorer(
            branch_type, protocol=self.protocol,
            mirror_stacked_on_url=self.default_stacked_on_url)

    def __init__(self, src, dest, branch_id, unique_name, branch_type,
                 default_stacked_on_url, protocol, branch_mirrorer=None):
        """Construct a `PullerWorker`.

        :param src: The URL to pull from.
        :param dest: The URL to pull into.
        :param branch_id: The database ID of the branch we're pulling.
        :param unique_name: The unique_name of the branch we're pulling
            (without the tilde).
        :param branch_type: A member of the BranchType enum.  It is expected
            that tests that do not depend on its value will pass None.
        :param default_stacked_on_url: The unique name of the default
            stacked-on branch for the product of the branch we are mirroring.
            None or '' if there is no such branch.
        :param protocol: An instance of `PullerWorkerProtocol`.
        :param branch_mirrorer: An instance of `BranchMirrorer`.  If not
            passed, one will be chosen based on the value of `branch_type`.
        """
        self.source = src
        self.dest = dest
        self.branch_id = branch_id
        self.unique_name = unique_name
        self.branch_type = branch_type
        if default_stacked_on_url == '':
            default_stacked_on_url = None
        self.default_stacked_on_url = default_stacked_on_url
        self.protocol = protocol
        if protocol is not None:
            self.protocol.branch_id = branch_id
        if branch_mirrorer is None:
            branch_mirrorer = self._checkerForBranchType(branch_type)
        self.branch_mirrorer = branch_mirrorer

    def _record_oops(self, message=None):
        """Record an oops for the current exception.

        This must only be called while handling an exception.

        :param message: custom explanatory error message. Do not use
            str(exception) to fill in this parameter, it should only be set
            when a human readable error has been explicitly generated.
        """
        request = errorlog.ScriptRequest([
            ('branch_id', self.branch_id), ('source', self.source),
            ('dest', self.dest), ('error-explanation', str(message))])
        request.URL = get_canonical_url_for_branch_name(self.unique_name)
        errorlog.globalErrorUtility.raising(sys.exc_info(), request)
        return request.oopsid

    def _mirrorFailed(self, error):
        oops_id = self._record_oops(error)
        self.protocol.mirrorFailed(error, oops_id)

    def mirrorWithoutChecks(self):
        """Mirror the source branch to the destination branch.

        This method doesn't do any error handling or send any messages via the
        reporting protocol -- a "naked mirror", if you will. This is
        particularly useful for tests that want to mirror a branch and be
        informed immediately of any errors.

        :return: ``(branch, revid_before)``, where ``branch`` is the
            destination branch and ``revid_before`` was the tip revision
            *before* the mirroring process ran.
        """
        # Avoid circular import
        from lp.codehosting.vfs import get_rw_server

        server = get_rw_server()
        server.start_server()
        try:
            source_branch = self.branch_mirrorer.open(self.source)
            return self.branch_mirrorer.mirror(source_branch, self.dest)
        finally:
            server.stop_server()

    def mirror(self):
        """Open source and destination branches and pull source into
        destination.
        """
        self.protocol.startMirroring()
        try:
            dest_branch, revid_before, stacked_on_url = \
                self.mirrorWithoutChecks()
        # add further encountered errors from the production runs here
        # ------ HERE ---------
        #
        except urllib2.HTTPError as e:
            msg = str(e)
            if int(e.code) == httplib.UNAUTHORIZED:
                # Maybe this will be caught in bzrlib one day, and then we'll
                # be able to get rid of this.
                # https://launchpad.net/products/bzr/+bug/42383
                msg = "Authentication required."
            self._mirrorFailed(msg)

        except socket.error as e:
            msg = 'A socket error occurred: %s' % str(e)
            self._mirrorFailed(msg)

        except errors.UnsupportedFormatError as e:
            msg = ("Launchpad does not support branches from before "
                   "bzr 0.7. Please upgrade the branch using bzr upgrade.")
            self._mirrorFailed(msg)

        except errors.UnknownFormatError as e:
            self._mirrorFailed(e)

        except (errors.ParamikoNotPresent, BadUrlSsh) as e:
            msg = ("Launchpad cannot mirror branches from SFTP and SSH URLs."
                   " Please register a HTTP location for this branch.")
            self._mirrorFailed(msg)

        except BadUrlLaunchpad:
            msg = "Launchpad does not mirror branches from Launchpad."
            self._mirrorFailed(msg)

        except BadUrlScheme as e:
            msg = "Launchpad does not mirror %s:// URLs." % e.scheme
            self._mirrorFailed(msg)

        except errors.NotBranchError as e:
            hosted_branch_error = errors.NotBranchError(
                "lp:%s" % self.unique_name)
            message_by_type = {
                BranchType.HOSTED: str(hosted_branch_error),
                BranchType.IMPORTED: "Not a branch.",
                }
            msg = message_by_type.get(self.branch_type, str(e))
            self._mirrorFailed(msg)

        except BranchReferenceForbidden as e:
            msg = ("Branch references are not allowed for branches of type "
                   "%s." % (self.branch_type.title,))
            self._mirrorFailed(msg)

        except BranchLoopError as e:
            msg = "Circular branch reference."
            self._mirrorFailed(msg)

        except errors.BzrError as e:
            self._mirrorFailed(e)

        except InvalidURIError as e:
            self._mirrorFailed(e)

        except (KeyboardInterrupt, SystemExit):
            # Do not record OOPS for those exceptions.
            raise

        else:
            revid_after = dest_branch.last_revision()
            # XXX: Aaron Bentley 2008-06-13
            # Bazaar does not provide a public API for learning about
            # format markers.  Fix this in Bazaar, then here.
            control_string = dest_branch.bzrdir._format.get_format_string()
            if dest_branch._format.__class__ is BzrBranchFormat4:
                branch_string = BranchFormat.BZR_BRANCH_4.title
            else:
                branch_string = dest_branch._format.get_format_string()
            repository_format = dest_branch.repository._format
            if repository_format.__class__ is RepositoryFormat6:
                repository_string = RepositoryFormat.BZR_REPOSITORY_6.title
            elif repository_format.__class__ is RepositoryFormat5:
                repository_string = RepositoryFormat.BZR_REPOSITORY_5.title
            elif repository_format.__class__ is RepositoryFormat4:
                repository_string = RepositoryFormat.BZR_REPOSITORY_4.title
            else:
                repository_string = repository_format.get_format_string()
            self.protocol.branchChanged(
                stacked_on_url, revid_before, revid_after, control_string,
                branch_string, repository_string)

    def __eq__(self, other):
        return self.source == other.source and self.dest == other.dest

    def __repr__(self):
        return ("<PullerWorker source=%s dest=%s at %x>" %
                (self.source, self.dest, id(self)))


WORKER_ACTIVITY_PROGRESS_BAR = 'progress bar'
WORKER_ACTIVITY_NETWORK = 'network'


class PullerWorkerUIFactory(SilentUIFactory):
    """An UIFactory that always says yes to breaking locks."""

    def __init__(self, puller_worker_protocol):
        SilentUIFactory.__init__(self)
        self.puller_worker_protocol = puller_worker_protocol

    def confirm_action(self, prompt, confirmation_id, args):
        """If we're asked to break a lock like a stale lock of ours, say yes.
        """
        assert confirmation_id == 'bzrlib.lockdir.break', \
            "Didn't expect confirmation id %r" % (confirmation_id,)
        branch_id = self.puller_worker_protocol.branch_id
        prompt = prompt % args
        if get_lock_id_for_branch_id(branch_id) in prompt:
            return True
        else:
            return False

    def _progress_updated(self, task):
        self.puller_worker_protocol.progressMade(WORKER_ACTIVITY_PROGRESS_BAR)

    def report_transport_activity(self, transport, byte_count, direction):
        # <poolie> mwhudson: if you're feeling paranoid i suggest you check
        #          the 'action' or whatever it's called is 'read'/'write'
        # <poolie> if we add a soft timeout like 'no io for two seconds' then
        #          we'd make a new action
        if direction in ['read', 'write']:
            self.puller_worker_protocol.progressMade(WORKER_ACTIVITY_NETWORK)


def install_worker_ui_factory(puller_worker_protocol):
    """Install a special UIFactory for puller workers.

    Our factory does two things:

    1) Create progress bars that inform a PullerWorkerProtocol of progress.
    2) Break locks if and only if they appear to be stale locks
       created by another puller worker process.
    """
    bzrlib.ui.ui_factory = PullerWorkerUIFactory(puller_worker_protocol)


class MirroredBranchPolicy(BranchMirrorerPolicy):
    """Mirroring policy for MIRRORED branches.

    In summary:

     - follow references,
     - only open non-Launchpad http: and https: URLs.
    """

    def __init__(self, stacked_on_url=None):
        self.stacked_on_url = stacked_on_url

    def getStackedOnURLForDestinationBranch(self, source_branch,
                                            destination_url):
        """Return the stacked on URL for the destination branch.

        Mirrored branches are stacked on the default stacked-on branch of
        their product, except when we're mirroring the default stacked-on
        branch itself.
        """
        if self.stacked_on_url is None:
            return None
        stacked_on_url = urlutils.join(destination_url, self.stacked_on_url)
        if destination_url == stacked_on_url:
            return None
        return self.stacked_on_url

    def shouldFollowReferences(self):
        """See `BranchOpenPolicy.shouldFollowReferences`.

        We traverse branch references for MIRRORED branches because they
        provide a useful redirection mechanism and we want to be consistent
        with the bzr command line.
        """
        return True

    def transformFallbackLocation(self, branch, url):
        """See `BranchOpenPolicy.transformFallbackLocation`.

        For mirrored branches, we stack on whatever the remote branch claims
        to stack on, but this URL still needs to be checked.
        """
        return urlutils.join(branch.base, url), True

    def checkOneURL(self, url):
        """See `BranchOpenPolicy.checkOneURL`.

        We refuse to mirror from Launchpad or a ssh-like or file URL.
        """
        # Avoid circular import
        from lp.code.interfaces.branch import get_blacklisted_hostnames
        uri = URI(url)
        launchpad_domain = config.vhost.mainsite.hostname
        if uri.underDomain(launchpad_domain):
            raise BadUrlLaunchpad(url)
        for hostname in get_blacklisted_hostnames():
            if uri.underDomain(hostname):
                raise BadUrl(url)
        if uri.scheme in ['sftp', 'bzr+ssh']:
            raise BadUrlSsh(url)
        elif uri.scheme not in ['http', 'https']:
            raise BadUrlScheme(uri.scheme, url)


class ImportedBranchPolicy(BranchMirrorerPolicy):
    """Mirroring policy for IMPORTED branches.

    In summary:

     - don't follow references,
     - assert the URLs start with the prefix we expect for imported branches.
    """

    def createDestinationBranch(self, source_branch, destination_url):
        """See `BranchOpenPolicy.createDestinationBranch`.

        Because we control the process that creates import branches, a
        vfs-level copy is safe and more efficient than a bzr fetch.
        """
        source_transport = source_branch.bzrdir.root_transport
        dest_transport = get_transport(destination_url)
        while True:
            # We loop until the remote file list before and after the copy is
            # the same to catch the case where the remote side is being
            # mutated as we copy it.
            if dest_transport.has('.'):
                dest_transport.delete_tree('.')
            files_before = set(source_transport.iter_files_recursive())
            source_transport.copy_tree_to_transport(dest_transport)
            files_after = set(source_transport.iter_files_recursive())
            if files_before == files_after:
                break
        return Branch.open_from_transport(dest_transport)

    def shouldFollowReferences(self):
        """See `BranchOpenerPolicy.shouldFollowReferences`.

        We do not traverse references for IMPORTED branches because the
        code-import system should never produce branch references.
        """
        return False

    def transformFallbackLocation(self, branch, url):
        """See `BranchOpenerPolicy.transformFallbackLocation`.

        Import branches should not be stacked, ever.
        """
        raise AssertionError("Import branch unexpectedly stacked!")

    def checkOneURL(self, url):
        """See `BranchOpenerPolicy.checkOneURL`.

        If the URL we are mirroring from does not start how we expect the pull
        URLs of import branches to start, something has gone badly wrong, so
        we raise AssertionError if that's happened.
        """
        if not url.startswith(config.launchpad.bzr_imports_root_url):
            raise AssertionError(
                "Bogus URL for imported branch: %r" % url)


def make_branch_mirrorer(branch_type, protocol=None,
                         mirror_stacked_on_url=None):
    """Create a `BranchMirrorer` with the appropriate `BranchOpenerPolicy`.

    :param branch_type: A `BranchType` to select a policy by.
    :param protocol: Optional protocol for the mirrorer to work with.
        If given, its log will also be used.
    :param mirror_stacked_on_url: For mirrored branches, the default URL
        to stack on.  Ignored for other branch types.
    :return: A `BranchMirrorer`.
    """
    if branch_type == BranchType.MIRRORED:
        policy = MirroredBranchPolicy(mirror_stacked_on_url)
    elif branch_type == BranchType.IMPORTED:
        policy = ImportedBranchPolicy()
    else:
        raise AssertionError(
            "Unexpected branch type: %r" % branch_type)

    if protocol is not None:
        log_function = protocol.log
    else:
        log_function = None

    return BranchMirrorer(policy, protocol, log_function)
