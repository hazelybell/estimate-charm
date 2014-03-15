# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The code import worker. This imports code from foreign repositories."""

__metaclass__ = type
__all__ = [
    'BazaarBranchStore',
    'BzrImportWorker',
    'BzrSvnImportWorker',
    'CSCVSImportWorker',
    'CodeImportBranchOpenPolicy',
    'CodeImportSourceDetails',
    'CodeImportWorkerExitCode',
    'ForeignTreeStore',
    'GitImportWorker',
    'ImportWorker',
    'get_default_bazaar_branch_store',
    ]


import os
import shutil

# FIRST Ensure correct plugins are loaded. Do not delete this comment or the
# line below this comment.
import lp.codehosting

from bzrlib.branch import (
    Branch,
    InterBranch,
    )
from bzrlib.bzrdir import (
    BzrDir,
    BzrDirFormat,
    )
from bzrlib.errors import (
    ConnectionError,
    InvalidEntryName,
    NoRepositoryPresent,
    NoSuchFile,
    NotBranchError,
    TooManyRedirections,
    )
from bzrlib.transport import (
    get_transport_from_path,
    get_transport_from_url,
    )
import bzrlib.ui
from bzrlib.upgrade import upgrade
from bzrlib.urlutils import (
    join as urljoin,
    local_path_from_url,
    )
import cscvs
from cscvs.cmds import totla
import CVS
from lazr.uri import (
    InvalidURIError,
    URI,
    )
import SCM

from lp.code.enums import RevisionControlSystems
from lp.code.interfaces.branch import get_blacklisted_hostnames
from lp.code.interfaces.codehosting import (
    branch_id_alias,
    compose_public_url,
    )
from lp.codehosting.codeimport.foreigntree import (
    CVSWorkingTree,
    SubversionWorkingTree,
    )
from lp.codehosting.codeimport.tarball import (
    create_tarball,
    extract_tarball,
    )
from lp.codehosting.codeimport.uifactory import LoggingUIFactory
from lp.codehosting.safe_open import (
    BadUrl,
    BranchOpenPolicy,
    SafeBranchOpener,
    )
from lp.services.config import config
from lp.services.propertycache import cachedproperty


class CodeImportBranchOpenPolicy(BranchOpenPolicy):
    """Branch open policy for code imports.

    In summary:
     - follow references,
     - only open non-Launchpad URLs
     - only open the allowed schemes
    """

    allowed_schemes = ['http', 'https', 'svn', 'git', 'ftp', 'bzr']

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
        return urljoin(branch.base, url), True

    def checkOneURL(self, url):
        """See `BranchOpenPolicy.checkOneURL`.

        We refuse to mirror from Launchpad or a ssh-like or file URL.
        """
        try:
            uri = URI(url)
        except InvalidURIError:
            raise BadUrl(url)
        launchpad_domain = config.vhost.mainsite.hostname
        if uri.underDomain(launchpad_domain):
            raise BadUrl(url)
        for hostname in get_blacklisted_hostnames():
            if uri.underDomain(hostname):
                raise BadUrl(url)
        if uri.scheme not in self.allowed_schemes:
            raise BadUrl(url)


class CodeImportWorkerExitCode:
    """Exit codes used by the code import worker script."""

    SUCCESS = 0
    FAILURE = 1
    SUCCESS_NOCHANGE = 2
    SUCCESS_PARTIAL = 3
    FAILURE_INVALID = 4
    FAILURE_UNSUPPORTED_FEATURE = 5
    FAILURE_FORBIDDEN = 6
    FAILURE_REMOTE_BROKEN = 7


class BazaarBranchStore:
    """A place where Bazaar branches of code imports are kept."""

    def __init__(self, transport):
        """Construct a Bazaar branch store based at `transport`."""
        self.transport = transport

    def _getMirrorURL(self, db_branch_id):
        """Return the URL that `db_branch` is stored at."""
        return urljoin(self.transport.base, '%08x' % db_branch_id)

    def pull(self, db_branch_id, target_path, required_format,
             needs_tree=False, stacked_on_url=None):
        """Pull down the Bazaar branch of an import to `target_path`.

        :return: A Bazaar branch for the code import corresponding to the
            database branch with id `db_branch_id`.
        """
        remote_url = self._getMirrorURL(db_branch_id)
        try:
            remote_bzr_dir = BzrDir.open(remote_url)
        except NotBranchError:
            local_branch = BzrDir.create_branch_and_repo(
                target_path, format=required_format)
            if needs_tree:
                local_branch.bzrdir.create_workingtree()
            if stacked_on_url:
                local_branch.set_stacked_on_url(stacked_on_url)
            return local_branch
        # The proper thing to do here would be to call
        # "remote_bzr_dir.sprout()".  But 2a fetch slowly checks which
        # revisions are in the ancestry of the tip of the remote branch, which
        # we strictly don't care about, so we just copy the whole thing down
        # at the vfs level.
        control_dir = remote_bzr_dir.root_transport.relpath(
            remote_bzr_dir.transport.abspath('.'))
        target = get_transport_from_path(target_path)
        target_control = target.clone(control_dir)
        target_control.create_prefix()
        remote_bzr_dir.transport.copy_tree_to_transport(target_control)
        local_bzr_dir = BzrDir.open_from_transport(target)
        if local_bzr_dir.needs_format_conversion(format=required_format):
            try:
                local_bzr_dir.root_transport.delete_tree('backup.bzr')
            except NoSuchFile:
                pass
            upgrade(target_path, required_format, clean_up=True)
        if needs_tree:
            local_bzr_dir.create_workingtree()
        return local_bzr_dir.open_branch()

    def push(self, db_branch_id, bzr_branch, required_format,
             stacked_on_url=None):
        """Push up `bzr_branch` as the Bazaar branch for `code_import`.

        :return: A boolean that is true if the push was non-trivial
            (i.e. actually transferred revisions).
        """
        self.transport.create_prefix()
        target_url = self._getMirrorURL(db_branch_id)
        try:
            remote_branch = Branch.open(target_url)
        except NotBranchError:
            remote_branch = BzrDir.create_branch_and_repo(
                target_url, format=required_format)
            old_branch = None
        else:
            if remote_branch.bzrdir.needs_format_conversion(
                    required_format):
                # For upgrades, push to a new branch in
                # the new format. When done pushing,
                # retire the old .bzr directory and rename
                # the new one in place.
                old_branch = remote_branch
                upgrade_url = urljoin(target_url, "backup.bzr")
                try:
                    remote_branch.bzrdir.root_transport.delete_tree(
                        'backup.bzr')
                except NoSuchFile:
                    pass
                remote_branch = BzrDir.create_branch_and_repo(
                    upgrade_url, format=required_format)
            else:
                old_branch = None
        # This can be done safely, since only modern formats are used to
        # import to.
        if stacked_on_url is not None:
            remote_branch.set_stacked_on_url(stacked_on_url)
        pull_result = remote_branch.pull(bzr_branch, overwrite=True)
        # Because of the way we do incremental imports, there may be revisions
        # in the branch's repo that are not in the ancestry of the branch tip.
        # We need to transfer them too.
        remote_branch.repository.fetch(bzr_branch.repository)
        if old_branch is not None:
            # The format has changed; move the new format
            # branch in place.
            base_transport = old_branch.bzrdir.root_transport
            base_transport.delete_tree('.bzr')
            base_transport.rename("backup.bzr/.bzr", ".bzr")
            base_transport.rmdir("backup.bzr")
        return pull_result.old_revid != pull_result.new_revid


def get_default_bazaar_branch_store():
    """Return the default `BazaarBranchStore`."""
    return BazaarBranchStore(
        get_transport_from_url(config.codeimport.bazaar_branch_store))


class CodeImportSourceDetails:
    """The information needed to process an import.

    As the worker doesn't talk to the database, we don't use
    `CodeImport` objects for this.

    The 'fromArguments' and 'asArguments' methods convert to and from a form
    of the information suitable for passing around on executables' command
    lines.

    :ivar branch_id: The id of the branch associated to this code import, used
        for locating the existing import and the foreign tree.
    :ivar rcstype: 'svn', 'cvs', 'git', 'bzr-svn', 'bzr' as appropriate.
    :ivar url: The branch URL if rcstype in ['svn', 'bzr-svn',
        'git', 'bzr'], None otherwise.
    :ivar cvs_root: The $CVSROOT if rcstype == 'cvs', None otherwise.
    :ivar cvs_module: The CVS module if rcstype == 'cvs', None otherwise.
    """

    def __init__(self, branch_id, rcstype, url=None, cvs_root=None,
                 cvs_module=None, stacked_on_url=None):
        self.branch_id = branch_id
        self.rcstype = rcstype
        self.url = url
        self.cvs_root = cvs_root
        self.cvs_module = cvs_module
        self.stacked_on_url = stacked_on_url

    @classmethod
    def fromArguments(cls, arguments):
        """Convert command line-style arguments to an instance."""
        branch_id = int(arguments.pop(0))
        rcstype = arguments.pop(0)
        if rcstype in ['svn', 'bzr-svn', 'git', 'bzr']:
            url = arguments.pop(0)
            try:
                stacked_on_url = arguments.pop(0)
            except IndexError:
                stacked_on_url = None
            cvs_root = cvs_module = None
        elif rcstype == 'cvs':
            url = None
            stacked_on_url = None
            [cvs_root, cvs_module] = arguments
        else:
            raise AssertionError("Unknown rcstype %r." % rcstype)
        return cls(
            branch_id, rcstype, url, cvs_root, cvs_module, stacked_on_url)

    @classmethod
    def fromCodeImport(cls, code_import):
        """Convert a `CodeImport` to an instance."""
        branch = code_import.branch
        if branch.stacked_on is not None and not branch.stacked_on.private:
            stacked_path = branch_id_alias(branch.stacked_on)
            stacked_on_url = compose_public_url('http', stacked_path)
        else:
            stacked_on_url = None
        if code_import.rcs_type == RevisionControlSystems.SVN:
            return cls(
                branch.id, 'svn', str(code_import.url),
                stacked_on_url=stacked_on_url)
        elif code_import.rcs_type == RevisionControlSystems.BZR_SVN:
            return cls(
                branch.id, 'bzr-svn', str(code_import.url),
                stacked_on_url=stacked_on_url)
        elif code_import.rcs_type == RevisionControlSystems.CVS:
            return cls(
                branch.id, 'cvs',
                cvs_root=str(code_import.cvs_root),
                cvs_module=str(code_import.cvs_module))
        elif code_import.rcs_type == RevisionControlSystems.GIT:
            return cls(
                branch.id, 'git', str(code_import.url),
                stacked_on_url=stacked_on_url)
        elif code_import.rcs_type == RevisionControlSystems.BZR:
            return cls(
                branch.id, 'bzr', str(code_import.url),
                stacked_on_url=stacked_on_url)
        else:
            raise AssertionError("Unknown rcstype %r." % code_import.rcs_type)

    def asArguments(self):
        """Return a list of arguments suitable for passing to a child process.
        """
        result = [str(self.branch_id), self.rcstype]
        if self.rcstype in ['svn', 'bzr-svn', 'git', 'bzr']:
            result.append(self.url)
            if self.stacked_on_url is not None:
                result.append(self.stacked_on_url)
        elif self.rcstype == 'cvs':
            result.append(self.cvs_root)
            result.append(self.cvs_module)
        else:
            raise AssertionError("Unknown rcstype %r." % self.rcstype)
        return result


class ImportDataStore:
    """A store for data associated with an import.

    Import workers can store and retreive files into and from the store using
    `put()` and `fetch()`.

    So this store can find files stored by previous versions of this code, the
    files are stored at ``<BRANCH ID IN HEX>.<EXT>`` where BRANCH ID comes
    from the CodeImportSourceDetails used to construct the instance and EXT
    comes from the local name passed to `put` or `fetch`.
    """

    def __init__(self, transport, source_details):
        """Initialize an `ImportDataStore`.

        :param transport: The transport files will be stored on.
        :param source_details: The `CodeImportSourceDetails` object, used to
            know where to store files on the remote transport.
        """
        self.source_details = source_details
        self._transport = transport
        self._branch_id = source_details.branch_id

    def _getRemoteName(self, local_name):
        """Convert `local_name` to the name used to store a file.

        The algorithm is a little stupid for historical reasons: we chop off
        the extension and stick that on the end of the branch id from the
        source_details we were constructed with, in hex padded to 8
        characters.  For example 'tree.tar.gz' might become '0000a23d.tar.gz'
        or 'git.db' might become '00003e4.db'.

        :param local_name: The local name of the file to be stored.
        :return: The name to store the file as on the remote transport.
        """
        if '/' in local_name:
            raise AssertionError("local_name must be a name, not a path")
        dot_index = local_name.index('.')
        if dot_index < 0:
            raise AssertionError("local_name must have an extension.")
        ext = local_name[dot_index:]
        return '%08x%s' % (self._branch_id, ext)

    def fetch(self, filename, dest_transport=None):
        """Retrieve `filename` from the store.

        :param filename: The name of the file to retrieve (must be a filename,
            not a path).
        :param dest_transport: The transport to retrieve the file to,
            defaulting to ``get_transport_from_path('.')``.
        :return: A boolean, true if the file was found and retrieved, false
            otherwise.
        """
        if dest_transport is None:
            dest_transport = get_transport_from_path('.')
        remote_name = self._getRemoteName(filename)
        if self._transport.has(remote_name):
            dest_transport.put_file(
                filename, self._transport.get(remote_name))
            return True
        else:
            return False

    def put(self, filename, source_transport=None):
        """Put `filename` into the store.

        :param filename: The name of the file to store (must be a filename,
            not a path).
        :param source_transport: The transport to look for the file on,
            defaulting to ``get_transport('.')``.
        """
        if source_transport is None:
            source_transport = get_transport_from_path('.')
        remote_name = self._getRemoteName(filename)
        local_file = source_transport.get(filename)
        self._transport.create_prefix()
        try:
            self._transport.put_file(remote_name, local_file)
        finally:
            local_file.close()


class ForeignTreeStore:
    """Manages retrieving and storing foreign working trees.

    The code import system stores tarballs of CVS and SVN working trees on
    another system. The tarballs are kept in predictable locations based on
    the ID of the branch associated to the `CodeImport`.

    The tarballs are all kept in one directory. The filename of a tarball is
    XXXXXXXX.tar.gz, where 'XXXXXXXX' is the ID of the `CodeImport`'s branch
    in hex.
    """

    def __init__(self, import_data_store):
        """Construct a `ForeignTreeStore`.

        :param transport: A writable transport that points to the base
            directory where the tarballs are stored.
        :ptype transport: `bzrlib.transport.Transport`.
        """
        self.import_data_store = import_data_store

    def _getForeignTree(self, target_path):
        """Return a foreign tree object for `target_path`."""
        source_details = self.import_data_store.source_details
        if source_details.rcstype == 'svn':
            return SubversionWorkingTree(
                source_details.url, str(target_path))
        elif source_details.rcstype == 'cvs':
            return CVSWorkingTree(
                source_details.cvs_root, source_details.cvs_module,
                target_path)
        else:
            raise AssertionError(
                "unknown RCS type: %r" % source_details.rcstype)

    def archive(self, foreign_tree):
        """Archive the foreign tree."""
        local_name = 'foreign_tree.tar.gz'
        create_tarball(foreign_tree.local_path, 'foreign_tree.tar.gz')
        self.import_data_store.put(local_name)

    def fetch(self, target_path):
        """Fetch the foreign branch for `source_details` to `target_path`.

        If there is no tarball archived for `source_details`, then try to
        download (i.e. checkout) the foreign tree from its source repository,
        generally on a third party server.
        """
        try:
            return self.fetchFromArchive(target_path)
        except NoSuchFile:
            return self.fetchFromSource(target_path)

    def fetchFromSource(self, target_path):
        """Fetch the foreign tree for `source_details` to `target_path`."""
        branch = self._getForeignTree(target_path)
        branch.checkout()
        return branch

    def fetchFromArchive(self, target_path):
        """Fetch the foreign tree for `source_details` from the archive."""
        local_name = 'foreign_tree.tar.gz'
        if not self.import_data_store.fetch(local_name):
            raise NoSuchFile(local_name)
        extract_tarball(local_name, target_path)
        tree = self._getForeignTree(target_path)
        tree.update()
        return tree


class ImportWorker:
    """Oversees the actual work of a code import."""

    # Where the Bazaar working tree will be stored.
    BZR_BRANCH_PATH = 'bzr_branch'

    # Should `getBazaarBranch` create a working tree?
    needs_bzr_tree = True

    required_format = BzrDirFormat.get_default_format()

    def __init__(self, source_details, import_data_transport,
                 bazaar_branch_store, logger, opener_policy):
        """Construct an `ImportWorker`.

        :param source_details: A `CodeImportSourceDetails` object.
        :param bazaar_branch_store: A `BazaarBranchStore`. The import worker
            uses this to fetch and store the Bazaar branches that are created
            and updated during the import process.
        :param logger: A `Logger` to pass to cscvs.
        :param opener_policy: Policy object that decides what branches can
             be imported
        """
        self.source_details = source_details
        self.bazaar_branch_store = bazaar_branch_store
        self.import_data_store = ImportDataStore(
            import_data_transport, self.source_details)
        self._logger = logger
        self._opener_policy = opener_policy

    def getBazaarBranch(self):
        """Return the Bazaar `Branch` that we are importing into."""
        if os.path.isdir(self.BZR_BRANCH_PATH):
            shutil.rmtree(self.BZR_BRANCH_PATH)
        return self.bazaar_branch_store.pull(
            self.source_details.branch_id, self.BZR_BRANCH_PATH,
            self.required_format, self.needs_bzr_tree,
            stacked_on_url=self.source_details.stacked_on_url)

    def pushBazaarBranch(self, bazaar_branch):
        """Push the updated Bazaar branch to the server.

        :return: True if revisions were transferred.
        """
        return self.bazaar_branch_store.push(
            self.source_details.branch_id, bazaar_branch,
            self.required_format,
            stacked_on_url=self.source_details.stacked_on_url)

    def getWorkingDirectory(self):
        """The directory we should change to and store all scratch files in.
        """
        base = config.codeimportworker.working_directory_root
        dirname = 'worker-for-branch-%s' % self.source_details.branch_id
        return os.path.join(base, dirname)

    def run(self):
        """Run the code import job.

        This is the primary public interface to the `ImportWorker`. This
        method:

         1. Retrieves an up-to-date foreign tree to import.
         2. Gets the Bazaar branch to import into.
         3. Imports the foreign tree into the Bazaar branch. If we've
            already imported this before, we synchronize the imported Bazaar
            branch with the latest changes to the foreign tree.
         4. Publishes the newly-updated Bazaar branch, making it available to
            Launchpad users.
         5. Archives the foreign tree, so that we can update it quickly next
            time.
        """
        working_directory = self.getWorkingDirectory()
        if os.path.exists(working_directory):
            shutil.rmtree(working_directory)
        os.makedirs(working_directory)
        saved_pwd = os.getcwd()
        os.chdir(working_directory)
        try:
            return self._doImport()
        finally:
            shutil.rmtree(working_directory)
            os.chdir(saved_pwd)

    def _doImport(self):
        """Perform the import.

        :return: A CodeImportWorkerExitCode
        """
        raise NotImplementedError()


class CSCVSImportWorker(ImportWorker):
    """An ImportWorker for imports that use CSCVS.

    As well as invoking cscvs to do the import, this class also needs to
    manage a foreign working tree.
    """

    # Where the foreign working tree will be stored.
    FOREIGN_WORKING_TREE_PATH = 'foreign_working_tree'

    @cachedproperty
    def foreign_tree_store(self):
        return ForeignTreeStore(self.import_data_store)

    def getForeignTree(self):
        """Return the foreign branch object that we are importing from.

        :return: A `SubversionWorkingTree` or a `CVSWorkingTree`.
        """
        if os.path.isdir(self.FOREIGN_WORKING_TREE_PATH):
            shutil.rmtree(self.FOREIGN_WORKING_TREE_PATH)
        os.mkdir(self.FOREIGN_WORKING_TREE_PATH)
        return self.foreign_tree_store.fetch(self.FOREIGN_WORKING_TREE_PATH)

    def importToBazaar(self, foreign_tree, bazaar_branch):
        """Actually import `foreign_tree` into `bazaar_branch`.

        :param foreign_tree: A `SubversionWorkingTree` or a `CVSWorkingTree`.
        :param bazaar_tree: A `bzrlib.branch.Branch`, which must have a
            colocated working tree.
        """
        foreign_directory = foreign_tree.local_path
        bzr_directory = str(bazaar_branch.bzrdir.open_workingtree().basedir)

        scm_branch = SCM.branch(bzr_directory)
        last_commit = cscvs.findLastCscvsCommit(scm_branch)

        # If branch in `bazaar_tree` doesn't have any identifiable CSCVS
        # revisions, CSCVS "initializes" the branch.
        if last_commit is None:
            self._runToBaz(
                foreign_directory, "-SI", "MAIN.1", bzr_directory)

        # Now we synchronise the branch, that is, import all new revisions
        # from the foreign branch into the Bazaar branch. If we've just
        # initialized the Bazaar branch, then this means we import *all*
        # revisions.
        last_commit = cscvs.findLastCscvsCommit(scm_branch)
        self._runToBaz(
            foreign_directory, "-SC", "%s::" % last_commit, bzr_directory)

    def _runToBaz(self, source_dir, flags, revisions, bazpath):
        """Actually run the CSCVS utility that imports revisions.

        :param source_dir: The directory containing the foreign working tree
            that we are importing from.
        :param flags: Flags to pass to `totla.totla`.
        :param revisions: The revisions to import.
        :param bazpath: The directory containing the Bazaar working tree that
            we are importing into.
        """
        # XXX: JonathanLange 2008-02-08: We need better documentation for
        # `flags` and `revisions`.
        config = CVS.Config(source_dir)
        config.args = ["--strict", "-b", bazpath,
                       flags, revisions, bazpath]
        totla.totla(config, self._logger, config.args, SCM.tree(source_dir))

    def _doImport(self):
        foreign_tree = self.getForeignTree()
        bazaar_branch = self.getBazaarBranch()
        self.importToBazaar(foreign_tree, bazaar_branch)
        non_trivial = self.pushBazaarBranch(bazaar_branch)
        self.foreign_tree_store.archive(foreign_tree)
        if non_trivial:
            return CodeImportWorkerExitCode.SUCCESS
        else:
            return CodeImportWorkerExitCode.SUCCESS_NOCHANGE


class PullingImportWorker(ImportWorker):
    """An import worker for imports that can be done by a bzr plugin.

    Subclasses need to implement `probers`.
    """

    needs_bzr_tree = False

    @property
    def invalid_branch_exceptions(self):
        """Exceptions that indicate no (valid) remote branch is present."""
        raise NotImplementedError

    @property
    def unsupported_feature_exceptions(self):
        """The exceptions to consider for unsupported features."""
        raise NotImplementedError

    @property
    def broken_remote_exceptions(self):
        """The exceptions to consider for broken remote branches."""
        raise NotImplementedError

    @property
    def probers(self):
        """The probers that should be tried for this import."""
        raise NotImplementedError

    def getRevisionLimit(self):
        """Return maximum number of revisions to fetch (None for no limit).
        """
        return None

    def _doImport(self):
        self._logger.info("Starting job.")
        saved_factory = bzrlib.ui.ui_factory
        opener = SafeBranchOpener(self._opener_policy, self.probers)
        bzrlib.ui.ui_factory = LoggingUIFactory(logger=self._logger)
        try:
            self._logger.info(
                "Getting exising bzr branch from central store.")
            bazaar_branch = self.getBazaarBranch()
            try:
                remote_branch = opener.open(self.source_details.url)
            except TooManyRedirections:
                self._logger.info("Too many redirections.")
                return CodeImportWorkerExitCode.FAILURE_INVALID
            except NotBranchError:
                self._logger.info("No branch found at remote location.")
                return CodeImportWorkerExitCode.FAILURE_INVALID
            except BadUrl as e:
                self._logger.info("Invalid URL: %s" % e)
                return CodeImportWorkerExitCode.FAILURE_FORBIDDEN
            except ConnectionError as e:
                self._logger.info("Unable to open remote branch: %s" % e)
                return CodeImportWorkerExitCode.FAILURE_INVALID
            try:
                remote_branch_tip = remote_branch.last_revision()
                inter_branch = InterBranch.get(remote_branch, bazaar_branch)
                self._logger.info("Importing branch.")
                revision_limit = self.getRevisionLimit()
                inter_branch.fetch(limit=revision_limit)
                if bazaar_branch.repository.has_revision(remote_branch_tip):
                    pull_result = inter_branch.pull(overwrite=True)
                    if pull_result.old_revid != pull_result.new_revid:
                        result = CodeImportWorkerExitCode.SUCCESS
                    else:
                        result = CodeImportWorkerExitCode.SUCCESS_NOCHANGE
                else:
                    result = CodeImportWorkerExitCode.SUCCESS_PARTIAL
            except Exception as e:
                if e.__class__ in self.unsupported_feature_exceptions:
                    self._logger.info(
                        "Unable to import branch because of limitations in "
                        "Bazaar.")
                    self._logger.info(str(e))
                    return (
                        CodeImportWorkerExitCode.FAILURE_UNSUPPORTED_FEATURE)
                elif e.__class__ in self.invalid_branch_exceptions:
                    self._logger.info("Branch invalid: %s", str(e))
                    return CodeImportWorkerExitCode.FAILURE_INVALID
                elif e.__class__ in self.broken_remote_exceptions:
                    self._logger.info("Remote branch broken: %s", str(e))
                    return CodeImportWorkerExitCode.FAILURE_REMOTE_BROKEN
                else:
                    raise
            self._logger.info("Pushing local import branch to central store.")
            self.pushBazaarBranch(bazaar_branch)
            self._logger.info("Job complete.")
            return result
        finally:
            bzrlib.ui.ui_factory = saved_factory


class GitImportWorker(PullingImportWorker):
    """An import worker for Git imports.

    The only behaviour we add is preserving the 'git.db' shamap between runs.
    """

    @property
    def invalid_branch_exceptions(self):
        return [
            NoRepositoryPresent,
            NotBranchError,
            ConnectionError,
        ]

    @property
    def unsupported_feature_exceptions(self):
        from bzrlib.plugins.git.fetch import SubmodulesRequireSubtrees
        return [
            InvalidEntryName,
            SubmodulesRequireSubtrees,
        ]

    @property
    def broken_remote_exceptions(self):
        return []

    @property
    def probers(self):
        """See `PullingImportWorker.probers`."""
        from bzrlib.plugins.git import (
            LocalGitProber, RemoteGitProber)
        return [LocalGitProber, RemoteGitProber]

    def getRevisionLimit(self):
        """See `PullingImportWorker.getRevisionLimit`."""
        return config.codeimport.git_revisions_import_limit

    def getBazaarBranch(self):
        """See `ImportWorker.getBazaarBranch`.

        In addition to the superclass' behaviour, we retrieve bzr-git's
        caches, both legacy and modern, from the import data store and put
        them where bzr-git will find them in the Bazaar tree, that is at
        '.bzr/repository/git.db' and '.bzr/repository/git'.
        """
        branch = PullingImportWorker.getBazaarBranch(self)
        # Fetch the legacy cache from the store, if present.
        self.import_data_store.fetch(
            'git.db', branch.repository._transport)
        # The cache dir from newer bzr-gits is stored as a tarball.
        local_name = 'git-cache.tar.gz'
        if self.import_data_store.fetch(local_name):
            repo_transport = branch.repository._transport
            repo_transport.mkdir('git')
            git_db_dir = os.path.join(
                local_path_from_url(repo_transport.base), 'git')
            extract_tarball(local_name, git_db_dir)
        return branch

    def pushBazaarBranch(self, bazaar_branch):
        """See `ImportWorker.pushBazaarBranch`.

        In addition to the superclass' behaviour, we store bzr-git's cache
        directory at .bzr/repository/git in the import data store.
        """
        non_trivial = PullingImportWorker.pushBazaarBranch(
            self, bazaar_branch)
        repo_base = bazaar_branch.repository._transport.base
        git_db_dir = os.path.join(local_path_from_url(repo_base), 'git')
        local_name = 'git-cache.tar.gz'
        create_tarball(git_db_dir, local_name)
        self.import_data_store.put(local_name)
        return non_trivial


class BzrSvnImportWorker(PullingImportWorker):
    """An import worker for importing Subversion via bzr-svn."""

    @property
    def invalid_branch_exceptions(self):
        return [
            NoRepositoryPresent,
            NotBranchError,
            ConnectionError,
        ]

    @property
    def unsupported_feature_exceptions(self):
        from bzrlib.plugins.svn.errors import InvalidFileName
        return [
            InvalidEntryName,
            InvalidFileName,
        ]

    @property
    def broken_remote_exceptions(self):
        from bzrlib.plugins.svn.errors import IncompleteRepositoryHistory
        return [IncompleteRepositoryHistory]

    def getRevisionLimit(self):
        """See `PullingImportWorker.getRevisionLimit`."""
        return config.codeimport.svn_revisions_import_limit

    @property
    def probers(self):
        """See `PullingImportWorker.probers`."""
        from bzrlib.plugins.svn import SvnRemoteProber
        return [SvnRemoteProber]


class BzrImportWorker(PullingImportWorker):
    """An import worker for importing Bazaar branches."""

    invalid_branch_exceptions = [
        NotBranchError,
        ConnectionError,
        ]
    unsupported_feature_exceptions = []
    broken_remote_exceptions = []

    def getRevisionLimit(self):
        """See `PullingImportWorker.getRevisionLimit`."""
        # For now, just grab the whole branch at once.
        # bzr does support fetch(limit=) but it isn't very efficient at
        # the moment.
        return None

    @property
    def probers(self):
        """See `PullingImportWorker.probers`."""
        from bzrlib.bzrdir import BzrProber, RemoteBzrProber
        return [BzrProber, RemoteBzrProber]
