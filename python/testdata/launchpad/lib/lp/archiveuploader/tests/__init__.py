# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the archive uploader."""

__metaclass__ = type

__all__ = [
    'datadir',
    'getPolicy',
    'insertFakeChangesFile',
    'insertFakeChangesFileForAllPackageUploads',
    ]

import os

from zope.component import getGlobalSiteManager

from lp.archiveuploader.uploadpolicy import (
    AbstractUploadPolicy,
    findPolicyByName,
    IArchiveUploadPolicy,
    )
from lp.services.librarianserver.testing.server import fillLibrarianFile
from lp.soyuz.model.queue import PackageUploadSet


here = os.path.dirname(os.path.realpath(__file__))


def datadir(path):
    """Return fully-qualified path inside the test data directory."""
    if path.startswith("/"):
        raise ValueError("Path is not relative: %s" % path)
    return os.path.join(here, 'data', path)


def insertFakeChangesFile(fileID, path=None):
    """Insert a fake changes file into the librarian.

    :param fileID: Use this as the librarian's file ID.
    :param path: If specified, use the changes file at "path",
                 otherwise the changes file for ed-0.2-21 is used.
    """
    if path is None:
        path = datadir("ed-0.2-21/ed_0.2-21_source.changes")
    with open(path, 'r') as changes_file_obj:
        test_changes_file = changes_file_obj.read()
    fillLibrarianFile(fileID, content=test_changes_file)


def insertFakeChangesFileForAllPackageUploads():
    """Ensure all the PackageUpload records point to a valid changes file."""
    for id in set(pu.changesfile.id for pu in PackageUploadSet()):
        insertFakeChangesFile(id)


class MockUploadOptions:
    """Mock upload policy options helper"""

    def __init__(self, distro='ubuntutest', distroseries=None):
        self.distro = distro
        self.distroseries = distroseries


def getPolicy(name='anything', distro='ubuntu', distroseries=None):
    """Build and return an Upload Policy for the given context."""
    policy = findPolicyByName(name)
    options = MockUploadOptions(distro, distroseries)
    policy.setOptions(options)
    return policy


class AnythingGoesUploadPolicy(AbstractUploadPolicy):
    """This policy is invoked when processing uploads from the test process.

    We require a signed changes file but that's it.
    """

    name = 'anything'

    def __init__(self):
        AbstractUploadPolicy.__init__(self)
        # We require the changes to be signed but not the dsc
        self.unsigned_dsc_ok = True

    def validateUploadType(self, upload):
        """We accept uploads of any type."""
        pass

    def policySpecificChecks(self, upload):
        """Nothing, let it go."""
        pass

    def rejectPPAUploads(self, upload):
        """We allow PPA uploads."""
        return False


class AbsolutelyAnythingGoesUploadPolicy(AnythingGoesUploadPolicy):
    """This policy is invoked when processing uploads from the test process.

    Absolutely everything is allowed, for when you don't want the hassle
    of dealing with inappropriate checks in tests.
    """

    name = 'absolutely-anything'

    def __init__(self):
        AnythingGoesUploadPolicy.__init__(self)
        self.unsigned_changes_ok = True

    def policySpecificChecks(self, upload):
        """Nothing, let it go."""
        pass


def register_archive_upload_policy_adapters():
    policies = [
        AnythingGoesUploadPolicy, AbsolutelyAnythingGoesUploadPolicy]
    sm = getGlobalSiteManager()
    for policy in policies:
        sm.registerUtility(
            component=policy, provided=IArchiveUploadPolicy, name=policy.name)
