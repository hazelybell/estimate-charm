# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Server classes that know how to create various kinds of foreign archive."""

__all__ = [
    'BzrServer',
    'CVSServer',
    'GitServer',
    'SubversionServer',
    ]

__metaclass__ = type

from cStringIO import StringIO
import errno
import os
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time

from bzrlib.branch import Branch
from bzrlib.branchbuilder import BranchBuilder
from bzrlib.bzrdir import BzrDir
from bzrlib.tests.test_server import (
    ReadonlySmartTCPServer_for_testing,
    TestServer,
    )
from bzrlib.tests.treeshape import build_tree_contents
from bzrlib.transport import Server
from bzrlib.urlutils import (
    escape,
    join as urljoin,
    )
import CVS
import dulwich.index
from dulwich.objects import Blob
from dulwich.repo import Repo as GitRepo
from dulwich.server import (
    DictBackend,
    TCPGitServer,
    )
import subvertpy.ra
import subvertpy.repos

from lp.services.log.logger import BufferLogger


def local_path_to_url(local_path):
    """Return a file:// URL to `local_path`.

    This implementation is unusual in that it returns a file://localhost/ URL.
    This is to work around the valid_vcs_details constraint on CodeImport.
    """
    return 'file://localhost' + escape(
        os.path.normpath(os.path.abspath(local_path)))


def run_in_temporary_directory(function):
    """Decorate `function` to be run in a temporary directory.

    Creates a new temporary directory and changes to it for the duration of
    `function`.
    """

    def decorated(*args, **kwargs):
        old_cwd = os.getcwd()
        new_dir = tempfile.mkdtemp()
        os.chdir(new_dir)
        try:
            return function(*args, **kwargs)
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(new_dir)

    decorated.__name__ = function.__name__
    decorated.__doc__ = function.__doc__
    return decorated


class SubversionServer(Server):
    """A controller for an Subversion repository, used for testing."""

    def __init__(self, repository_path, use_svn_serve=False):
        super(SubversionServer, self).__init__()
        self.repository_path = os.path.abspath(repository_path)
        self._use_svn_serve = use_svn_serve

    def _get_ra(self, url):
        return subvertpy.ra.RemoteAccess(url,
            auth=subvertpy.ra.Auth([subvertpy.ra.get_username_provider()]))

    def createRepository(self, path):
        """Create a Subversion repository at `path`."""
        subvertpy.repos.create(path)

    def get_url(self):
        """Return a URL to the Subversion repository."""
        if self._use_svn_serve:
            return 'svn://localhost/'
        else:
            return local_path_to_url(self.repository_path)

    def start_server(self):
        super(SubversionServer, self).start_server()
        self.createRepository(self.repository_path)
        if self._use_svn_serve:
            conf_path = os.path.join(
                self.repository_path, 'conf/svnserve.conf')
            with open(conf_path, 'w') as conf_file:
                conf_file.write('[general]\nanon-access = write\n')
            self._svnserve = subprocess.Popen(
                ['svnserve', '--daemon', '--foreground', '--threads',
                 '--root', self.repository_path])
            delay = 0.1
            for i in range(10):
                try:
                    self._get_ra(self.get_url())
                except OSError as e:
                    if e.errno == errno.ECONNREFUSED:
                        time.sleep(delay)
                        delay *= 1.5
                        continue
                else:
                    break
            else:
                self._kill_svnserve()
                raise AssertionError(
                    "svnserve didn't start accepting connections")

    def _kill_svnserve(self):
        os.kill(self._svnserve.pid, signal.SIGINT)
        self._svnserve.communicate()

    def stop_server(self):
        super(SubversionServer, self).stop_server()
        if self._use_svn_serve:
            self._kill_svnserve()

    def makeBranch(self, branch_name, tree_contents):
        """Create a branch on the Subversion server called `branch_name`.

        :param branch_name: The name of the branch to create.
        :param tree_contents: The contents of the module. This is a list of
            tuples of (relative filename, file contents).
        """
        branch_url = self.makeDirectory(branch_name)
        ra = self._get_ra(branch_url)
        editor = ra.get_commit_editor({"svn:log": "Import"})
        root = editor.open_root()
        for filename, content in tree_contents:
            f = root.add_file(filename)
            try:
                subvertpy.delta.send_stream(StringIO(content),
                    f.apply_textdelta())
            finally:
                f.close()
        root.close()
        editor.close()
        return branch_url

    def makeDirectory(self, directory_name, commit_message=None):
        """Make a directory on the repository."""
        if commit_message is None:
            commit_message = 'Make %r' % (directory_name,)
        ra = self._get_ra(self.get_url())
        editor = ra.get_commit_editor({"svn:log": commit_message})
        root = editor.open_root()
        root.add_directory(directory_name).close()
        root.close()
        editor.close()
        return urljoin(self.get_url(), directory_name)


class CVSServer(Server):
    """A CVS server for testing."""

    def __init__(self, repository_path):
        """Construct a `CVSServer`.

        :param repository_path: The path to the directory that will contain
            the CVS repository.
        """
        super(CVSServer, self).__init__()
        self._repository_path = os.path.abspath(repository_path)

    def createRepository(self, path):
        """Create a CVS repository at `path`.

        :param path: The local path to create a repository in.
        :return: A CVS.Repository`.
        """
        return CVS.init(path, BufferLogger())

    def getRoot(self):
        """Return the CVS root for this server."""
        return self._repository_path

    @run_in_temporary_directory
    def makeModule(self, module_name, tree_contents):
        """Create a module on the CVS server called `module_name`.

        A 'module' in CVS roughly corresponds to a project.

        :param module_name: The name of the module to create.
        :param tree_contents: The contents of the module. This is a list of
            tuples of (relative filename, file contents).
        """
        build_tree_contents(tree_contents)
        self._repository.Import(
            module=module_name, log="import", vendor="vendor",
            release=['release'], dir='.')

    def start_server(self):
        # Initialize the repository.
        super(CVSServer, self).start_server()
        self._repository = self.createRepository(self._repository_path)


class TCPGitServerThread(threading.Thread):
    """Thread that runs a TCP Git server."""

    def __init__(self, backend, address, port=None):
        super(TCPGitServerThread, self).__init__()
        self.setName("TCP Git server on %s:%s" % (address, port))
        self.server = TCPGitServer(backend, address, port)

    def run(self):
        self.server.serve_forever()

    def get_address(self):
        return self.server.server_address

    def stop(self):
        self.server.shutdown()


class GitServer(Server):

    def __init__(self, repository_path, use_server=False):
        super(GitServer, self).__init__()
        self.repository_path = repository_path
        self._use_server = use_server

    def get_url(self):
        """Return a URL to the Git repository."""
        if self._use_server:
            return 'git://%s:%d/' % self._server.get_address()
        else:
            return local_path_to_url(self.repository_path)

    def createRepository(self, path):
        GitRepo.init(path)

    def start_server(self):
        super(GitServer, self).start_server()
        self.createRepository(self.repository_path)
        if self._use_server:
            repo = GitRepo(self.repository_path)
            self._server = TCPGitServerThread(
                DictBackend({"/": repo}), "localhost", 0)
            self._server.start()

    def stop_server(self):
        super(GitServer, self).stop_server()
        if self._use_server:
            self._server.stop()

    def makeRepo(self, tree_contents):
        repo = GitRepo(self.repository_path)
        blobs = [
            (Blob.from_string(contents), filename) for (filename, contents)
            in tree_contents]
        repo.object_store.add_objects(blobs)
        root_id = dulwich.index.commit_tree(repo.object_store, [
            (filename, b.id, stat.S_IFREG | 0644)
            for (b, filename) in blobs])
        repo.do_commit(committer='Joe Foo <joe@foo.com>',
            message=u'<The commit message>', tree=root_id)


class BzrServer(Server):

    def __init__(self, repository_path, use_server=False):
        super(BzrServer, self).__init__()
        self.repository_path = repository_path
        self._use_server = use_server

    def createRepository(self, path):
        BzrDir.create_branch_convenience(path)

    def makeRepo(self, tree_contents):
        branch = Branch.open(self.repository_path)
        branch.get_config().set_user_option("create_signatures", "never")
        builder = BranchBuilder(branch=branch)
        actions = [('add', ('', 'tree-root', 'directory', None))]
        actions += [
            ('add', (path, path + '-id', 'file', content))
            for (path, content) in tree_contents]
        builder.build_snapshot(
            None, None, actions, committer='Joe Foo <joe@foo.com>',
                message=u'<The commit message>')

    def get_url(self):
        if self._use_server:
            return self._bzrserver.get_url()
        else:
            return local_path_to_url(self.repository_path)

    def start_server(self):
        super(BzrServer, self).start_server()
        self.createRepository(self.repository_path)

        class LocalURLServer(TestServer):
            def __init__(self, repository_path):
                self.repository_path = repository_path

            def start_server(self):
                pass

            def get_url(self):
                return local_path_to_url(self.repository_path)

        if self._use_server:
            self._bzrserver = ReadonlySmartTCPServer_for_testing()
            self._bzrserver.start_server(
                LocalURLServer(self.repository_path))

    def stop_server(self):
        super(BzrServer, self).stop_server()
        if self._use_server:
            self._bzrserver.stop_server()
