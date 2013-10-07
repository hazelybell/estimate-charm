# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""FakePackager utility.

It builds small and fully functional packages to be used in launchpad test
suite.
"""

__metaclass__ = type
__all__ = ['FakePackager']

import atexit
import os
import shutil
import subprocess
import tarfile
import tempfile
import time

from zope.component import getUtility

from lp.archiveuploader.nascentupload import NascentUpload
from lp.archiveuploader.uploadpolicy import findPolicyByName
from lp.registry.interfaces.distribution import IDistributionSet
from lp.services.gpg.interfaces import IGPGHandler
from lp.services.log.logger import BufferLogger
from lp.soyuz.enums import PackageUploadStatus
from lp.testing.gpgkeys import import_secret_test_key


changelog_entry_template = (
    """%(source_name)s (%(version)s) %(suite)s; urgency=low

  * %(changelog_text)s

 -- %(author)s <%(email)s>  %(timestamp)s

""")

control_file_template = """
Source: %(source)s
Section: %(section)s
Priority: %(priority)s
Maintainer: Launchpad team <launchpad@lists.canonical.com>
Standards-Version: 3.7.3

Package: %(binary)s
Architecture: %(arch)s
Section: %(section)s
Description: Stuff for testing
 This package is simply used for testing soyuz

"""

rules_file_template = """#!/usr/bin/make -f

build:
\t@echo Built

binary-indep:
\t@echo Nothing to do

binary-arch:
\tmkdir debian/tmp
\tmkdir debian/tmp/DEBIAN
\tcp contents debian/tmp/%(name)s-contents
\tdpkg-gencontrol -isp
\tdpkg-deb -b debian/tmp ..

clean:
\trm -rf debian/tmp

binary: binary-arch
"""


class FakePackager:
    """Builds small and fully functional debian source packages

    It uses a series of templates to build controllable sources to be
    used in Soyuz tests.
    """

    def __init__(self, name, version, key_path=None):
        """Create a 'sandbox' directory."""
        self._createNewSandbox()
        self.name = name
        self.version = version

        if key_path is not None:
            self.gpg_key_id = self._importGPGKey(key_path)
        else:
            self.gpg_key_id = None

        self.upstream_directory = os.path.join(
            self.sandbox_path, '%s-%s' % (self.name, self.version))

        # Upstream debian paths.
        self.debian_path = os.path.join(self.upstream_directory, 'debian')
        self.changelog_path = os.path.join(self.debian_path, 'changelog')
        self.copyright_path = os.path.join(self.debian_path, 'copyright')
        self.rules_path = os.path.join(self.debian_path, 'rules')
        self.control_path = os.path.join(self.debian_path, 'control')

    def _createNewSandbox(self):
        """Create the 'sandbox' path as a temporary directory.

        Also register an atexit handler to remove it on normal termination.
        """
        self.sandbox_path = tempfile.mkdtemp(prefix='fakepackager-')

        def removeSandbox(sandbox):
            """Remove sandbox directory if it exists."""
            if os.path.exists(sandbox):
                shutil.rmtree(sandbox)
        atexit.register(removeSandbox, self.sandbox_path)

    def _importGPGKey(self, key_path):
        """Import the given secret GPG key to sign packages.

        Return the key ID import as '0xAABBCCDD'
        """
        gpghandler = getUtility(IGPGHandler)

        if key_path is None:
            self.gpg_key_id = None
            return

        gpghandler.resetLocalState()
        import_secret_test_key(key_path)
        key = list(gpghandler.localKeys())[0]

        return '0x%s' % key.keyid

    def _appendContents(self, content):
        """Append a given content in the upstream 'contents' file.

        Use this method to add arbitrary content to this non-debian file.
        """
        contents_file = open(
            os.path.join(self.upstream_directory, 'contents'), 'a')
        contents_file.write("%s\n" % content)
        contents_file.close()

    def _buildOrig(self):
        """Build a gzip tarball of the current 'upstream_directory'.

        The tarball will be named 'name_version.orig.tar.gz' and located
        at the sandbox root.
        """
        orig_filename = '%s_%s.orig.tar.gz' % (self.name, self.version)
        orig_path = os.path.join(self.sandbox_path, orig_filename)
        orig = tarfile.open(orig_path, 'w:gz')
        orig.add(self.upstream_directory)
        orig.close()

    def _createFile(self, path, content=''):
        """Create a file in the given path with the given content.

        A new line is appended at the end of the file.
        """
        fd = open(path, 'w')
        fd.write('%s\n' % content)
        fd.close()

    def _populateChangelog(self):
        """Create an empty debian/changelog """
        self._createFile(self.changelog_path)

    def _populateControl(self, section=None, arch=None):
        """Create the debian/control using 'control_file_template'."""
        if section is None:
            section = 'devel'

        if arch is None:
            arch = 'any'

        replacements = {
            'source': self.name,
            'binary': self.name,
            'section': section,
            'priority': 'optional',
            'arch': arch,
            }
        self._createFile(
            self.control_path, control_file_template % replacements)

    def _populateCopyright(self):
        """Create a placeholder debian/copyright."""
        self._createFile(
            self.copyright_path, 'No ones land ...')

    def _populateRules(self):
        """Create the debian/rules using 'rules_file_template'."""
        replacements = {
            'name': self.name,
            }
        self._createFile(
            self.rules_path, rules_file_template % replacements)

    def _populateDebian(self, section, arch):
        """Create and populate a minimal debian directory."""
        os.mkdir(self.debian_path)
        self._populateChangelog()
        self._populateControl(section, arch)
        self._populateCopyright()
        self._populateRules()

    def _prependChangelogEntry(self, changelog_replacements):
        """Prepend a changelog entry in the current upstream directory."""
        changelog_file = open(self.changelog_path)
        previous_content = changelog_file.read()
        changelog_file.close()

        changelog_entry = changelog_entry_template % changelog_replacements
        changelog_file = open(self.changelog_path, 'w')
        changelog_file.write(changelog_entry)
        changelog_file.write(previous_content)
        changelog_file.close()

    def _runSubProcess(self, script, extra_args=None):
        """Run the given script and collects STDOUT and STDERR.

        :raises AssertionError: If the script returns a non-Zero value.
        """
        if extra_args is None:
            extra_args = []
        args = [script]
        args.extend(extra_args)
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        assert process.returncode == 0, (
            'Out:\n%sErr:\n%s' % (stdout, stderr))

        return (stdout, stderr)

    def _getChangefilePathForVersion(self, version, type='source'):
        """Return the changesfile path for a given (version, type).

        'type' defaults to 'source' but can also be a architecturetag
        for binary uploads. It respects the context 'name'.

        Return None if the specified upload could not be found.
        """
        changesfile_name = "%s_%s_%s.changes" % (self.name, version, type)
        changesfile_path = os.path.join(self.sandbox_path, changesfile_name)

        if os.path.exists(changesfile_path):
            return changesfile_path

        return None

    def _doUpload(self, type, version, policy, archive, distribution_name,
                  suite, logger, notify):
        """Upload a given version.

        Raises an error if the version couldn't be found or the upload
        was rejected.

        Build a upload policy with the given name and override it with
        archive, distribution_name and suite if passed.

        Return the corresponding `NascentUpload` object.
        """
        changesfile_path = self._getChangefilePathForVersion(version, type)
        assert changesfile_path is not None, (
            "Could not find a %s upload for version %s." % (type, version))

        if archive is not None:
            policy.archive = archive

        policy.distro = getUtility(IDistributionSet).getByName(
            distribution_name)

        if suite is not None:
            policy.setDistroSeriesAndPocket(suite)

        upload = NascentUpload.from_changesfile_path(
            changesfile_path, policy, logger)
        upload.process()

        return upload

    def buildUpstream(self, suite='hoary', section=None, arch=None,
                      build_orig=True):
        """Build a fake source upstream version.

        This method should only be called once for a given upstream-{name,
        version}.

        :param build_orig: boolean indicating whether or not to prepare
             a orig.tar.gz containing the pristine upstream code. If
             generated it can be used for subsequent versions.

        :raises AssertionError: if there is already a upstream directory
            for the context upstream-{name, version}.
        """
        assert not os.path.exists(self.upstream_directory), (
            'Selected upstream directory already exists: %s' % (
                os.path.basename(self.upstream_directory)))

        os.mkdir(self.upstream_directory)
        self._appendContents(self.version)

        if build_orig:
            self._buildOrig()

        self._populateDebian(section, arch)

        first_version = '%s-1' % self.version
        self.buildVersion(
            first_version, suite=suite, section=section, arch=arch,
            changelog_text='Initial Upstream package')

    def buildVersion(self, version, changelog_text="nicht !",
                     suite='hoary', section=None, arch=None, author='Foo Bar',
                     email='foo.bar@canonical.com', timestamp=None):
        """Initialize a new version of extracted package."""
        assert version.startswith(self.version), (
            'New versions should start with the upstream version: %s ' % (
                self.version))

        if timestamp is None:
            timestamp = time.strftime('%a, %d %b %Y %T %z')

        self._populateControl(section, arch)

        changelog_replacements = {
            'source_name': self.name,
            'version': version,
            'suite': suite,
            'changelog_text': changelog_text,
            'author': author,
            'email': email,
            'timestamp': timestamp,
            }

        self._prependChangelogEntry(changelog_replacements)
        self._appendContents(version)

    def buildSource(self, include_orig=True, signed=True):
        """Build a new version of the source package.

        :param  include_orig: boolean, controls whether or not the
             upstream tarball should be included in the changesfile.
        :param signed: whether or not to build a signed package.

        :raises AssertionError: if the upstream directory is not available
            or if no GPG key was imported by this object.
        """
        assert os.path.exists(self.upstream_directory), (
            'Selected upstream directory does not exist: %s' % (
                os.path.basename(self.upstream_directory)))

        debuild_options = ['--no-conf', '-S']

        if not signed:
            debuild_options.extend(['-uc', '-us'])
        else:
            assert self.gpg_key_id is not None, (
                'Cannot build signed packages because the key is not set.')
            debuild_options.append('-k%s' % self.gpg_key_id)

        if include_orig:
            debuild_options.append('-sa')

        current_path = os.getcwd()
        os.chdir(self.upstream_directory)

        self._runSubProcess('debuild', debuild_options)

        os.chdir(current_path)

    def listAvailableUploads(self):
        """Return the path for all available changesfiles."""
        changes = [os.path.join(self.sandbox_path, filename)
                   for filename in os.listdir(self.sandbox_path)
                   if filename.endswith('.changes')]

        return sorted(changes)

    def uploadSourceVersion(self, version, policy='insecure', archive=None,
                            distribution_name='ubuntu', suite=None,
                            logger=None, notify=False, auto_accept=True):
        """Upload and publish a source package from the sandbox directory.

        See `_doUpload`.

        If 'auto_accept' is true, accept the upload if necessary and return
        the corresponding `ISourcePackagePublishingHistory` record. Otherwise
        return the corresponding `NascentUpload` object.
        """
        policy = findPolicyByName(policy)

        if logger is None:
            logger = BufferLogger()

        upload = self._doUpload(
            'source', version, policy, archive, distribution_name, suite,
            logger, notify)

        if not auto_accept:
            return upload

        if not upload.is_rejected:
            upload.do_accept(notify=notify)

        assert not upload.is_rejected, (
            "Upload was rejected: %s" % upload.rejection_message)

        queue_record = upload.queue_root
        needs_acceptance_statuses = (
            PackageUploadStatus.NEW,
            PackageUploadStatus.UNAPPROVED,
            )
        changesfile_path = self._getChangefilePathForVersion(
            version, 'source')
        if queue_record.status in needs_acceptance_statuses:
            queue_record.acceptFromUploader(changesfile_path, logger)

        return queue_record.archive.getPublishedSources(
            name=self.name, version=version, exact_match=True).first()
