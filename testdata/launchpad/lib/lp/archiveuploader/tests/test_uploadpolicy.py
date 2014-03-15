#!/usr/bin/python
#
# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from zope.component import getUtility
from zope.component.interfaces import ComponentLookupError

from lp.app.errors import NotFoundError
from lp.archiveuploader.nascentuploadfile import CustomUploadFile
from lp.archiveuploader.uploadpolicy import (
    AbstractUploadPolicy,
    ArchiveUploadType,
    findPolicyByName,
    IArchiveUploadPolicy,
    InsecureUploadPolicy,
    )
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.services.database.sqlbase import flush_database_updates
from lp.testing import (
    celebrity_logged_in,
    person_logged_in,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class FakeNascentUpload:

    def __init__(self, sourceful, binaryful, is_ppa):
        self.sourceful = sourceful
        self.binaryful = binaryful
        self.is_ppa = is_ppa
        self.rejections = []

    def reject(self, msg):
        self.rejections.append(msg)


def make_fake_upload(sourceful=False, binaryful=False, is_ppa=False):
    return FakeNascentUpload(sourceful, binaryful, is_ppa)


def make_policy(accepted_type):
    policy = AbstractUploadPolicy()
    policy.accepted_type = accepted_type
    return policy


class FakeOptions:
    def __init__(self, distroseries=None):
        self.distro = "ubuntu"
        self.distroseries = distroseries


class FakeChangesFile:
    def __init__(self, custom_files=[]):
        self.custom_files = custom_files


class TestUploadPolicy_validateUploadType(TestCase):
    """Test what kind (sourceful/binaryful/mixed) of uploads are accepted."""

    def test_sourceful_accepted(self):
        policy = make_policy(accepted_type=ArchiveUploadType.SOURCE_ONLY)
        upload = make_fake_upload(sourceful=True)

        policy.validateUploadType(upload)

        self.assertEquals([], upload.rejections)

    def test_binaryful_accepted(self):
        policy = make_policy(accepted_type=ArchiveUploadType.BINARY_ONLY)
        upload = make_fake_upload(binaryful=True)

        policy.validateUploadType(upload)

        self.assertEquals([], upload.rejections)

    def test_mixed_accepted(self):
        policy = make_policy(accepted_type=ArchiveUploadType.MIXED_ONLY)
        upload = make_fake_upload(sourceful=True, binaryful=True)

        policy.validateUploadType(upload)

        self.assertEquals([], upload.rejections)

    def test_sourceful_not_accepted(self):
        policy = make_policy(accepted_type=ArchiveUploadType.BINARY_ONLY)
        upload = make_fake_upload(sourceful=True)

        policy.validateUploadType(upload)

        self.assertIn(
            'Sourceful uploads are not accepted by this policy.',
            upload.rejections)

    def test_binaryful_not_accepted(self):
        policy = make_policy(accepted_type=ArchiveUploadType.SOURCE_ONLY)
        upload = make_fake_upload(binaryful=True)

        policy.validateUploadType(upload)

        self.assertTrue(len(upload.rejections) > 0)
        self.assertIn(
            'Upload rejected because it contains binary packages.',
            upload.rejections[0])

    def test_mixed_not_accepted(self):
        policy = make_policy(accepted_type=ArchiveUploadType.SOURCE_ONLY)
        upload = make_fake_upload(sourceful=True, binaryful=True)

        policy.validateUploadType(upload)

        self.assertIn(
            'Source/binary (i.e. mixed) uploads are not allowed.',
            upload.rejections)

    def test_sourceful_when_only_mixed_accepted(self):
        policy = make_policy(accepted_type=ArchiveUploadType.MIXED_ONLY)
        upload = make_fake_upload(sourceful=True, binaryful=False)

        policy.validateUploadType(upload)

        self.assertIn(
            'Sourceful uploads are not accepted by this policy.',
            upload.rejections)

    def test_binaryful_when_only_mixed_accepted(self):
        policy = make_policy(accepted_type=ArchiveUploadType.MIXED_ONLY)
        upload = make_fake_upload(sourceful=False, binaryful=True)

        policy.validateUploadType(upload)

        self.assertTrue(len(upload.rejections) > 0)
        self.assertIn(
            'Upload rejected because it contains binary packages.',
            upload.rejections[0])


class TestUploadPolicy(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_getUtility_returns_class(self):
        # Since upload policies need to be changed according to
        # user-specified arguments, the utility for looking up policies
        # returns the class itself rather than an instance of it.
        policy_cls = getUtility(IArchiveUploadPolicy, "insecure")
        self.assertIs(InsecureUploadPolicy, policy_cls)

    def test_findPolicyByName_returns_instance(self):
        # There is a helper function that returns an instance of the policy
        # with the given name.  It is preferred over using getUtility()
        # directly.
        insecure_policy = findPolicyByName("insecure")
        self.assertIsInstance(insecure_policy, InsecureUploadPolicy)

    def test_policy_names(self):
        self.assertEqual("insecure", findPolicyByName("insecure").name)
        self.assertEqual("buildd", findPolicyByName("buildd").name)

    def test_cannot_look_up_abstract_policy(self):
        self.assertRaises(ComponentLookupError, findPolicyByName, "abstract")

    def test_policy_attributes(self):
        # Some attributes are expected to exist but vary between policies.
        insecure_policy = findPolicyByName("insecure")
        buildd_policy = findPolicyByName("buildd")
        self.assertFalse(insecure_policy.unsigned_changes_ok)
        self.assertTrue(buildd_policy.unsigned_changes_ok)
        self.assertFalse(insecure_policy.unsigned_dsc_ok)
        self.assertTrue(buildd_policy.unsigned_dsc_ok)

    def test_setOptions_distro_name(self):
        # Policies pick up the distribution name from options.
        for policy_name in "insecure", "buildd":
            policy = findPolicyByName(policy_name)
            policy.setOptions(FakeOptions())
            self.assertEqual("ubuntu", policy.distro.name)

    def test_setOptions_distroseries_name(self):
        # If a distroseries name is set, the policy picks it up from option.
        buildd_policy = findPolicyByName("buildd")
        buildd_policy.setOptions(FakeOptions(distroseries="hoary"))
        self.assertEqual("hoary", buildd_policy.distroseries.name)

    def test_setDistroSeriesAndPocket_distro_not_found(self):
        policy = AbstractUploadPolicy()
        policy.distro = self.factory.makeDistribution()
        self.assertRaises(
            NotFoundError, policy.setDistroSeriesAndPocket,
            'nonexistent_security')

    def test_setDistroSeriesAndPocket_honours_aliases(self):
        # setDistroSeriesAndPocket honours uploads to the development series
        # alias, if set.
        policy = AbstractUploadPolicy()
        policy.distro = self.factory.makeDistribution()
        series = self.factory.makeDistroSeries(
            distribution=policy.distro, status=SeriesStatus.DEVELOPMENT)
        self.assertRaises(
            NotFoundError, policy.setDistroSeriesAndPocket, "devel")
        with person_logged_in(policy.distro.owner):
            policy.distro.development_series_alias = "devel"
        policy.setDistroSeriesAndPocket("devel")
        self.assertEqual(series, policy.distroseries)

    def test_redirect_release_uploads_primary(self):
        # With the insecure policy, the
        # Distribution.redirect_release_uploads flag causes uploads to the
        # RELEASE pocket to be automatically redirected to PROPOSED.
        ubuntu = getUtility(IDistributionSet)["ubuntu"]
        with celebrity_logged_in("admin"):
            ubuntu.redirect_release_uploads = True
        flush_database_updates()
        insecure_policy = findPolicyByName("insecure")
        insecure_policy.setOptions(FakeOptions(distroseries="hoary"))
        self.assertEqual("hoary", insecure_policy.distroseries.name)
        self.assertEqual(
            PackagePublishingPocket.PROPOSED, insecure_policy.pocket)

    def test_redirect_release_uploads_ppa(self):
        # The Distribution.redirect_release_uploads flag does not affect PPA
        # uploads.
        ubuntu = getUtility(IDistributionSet)["ubuntu"]
        with celebrity_logged_in("admin"):
            ubuntu.redirect_release_uploads = True
        flush_database_updates()
        insecure_policy = findPolicyByName("insecure")
        insecure_policy.archive = self.factory.makeArchive()
        insecure_policy.setOptions(FakeOptions(distroseries="hoary"))
        self.assertEqual("hoary", insecure_policy.distroseries.name)
        self.assertEqual(
            PackagePublishingPocket.RELEASE, insecure_policy.pocket)

    def setHoaryStatus(self, status):
        ubuntu = getUtility(IDistributionSet)["ubuntu"]
        with celebrity_logged_in("admin"):
            ubuntu["hoary"].status = status
        flush_database_updates()

    def test_insecure_approves_release(self):
        # Uploads to the RELEASE pocket of non-FROZEN distroseries are
        # approved by the insecure policy.
        insecure_policy = findPolicyByName("insecure")
        insecure_policy.setOptions(FakeOptions(distroseries="hoary"))
        self.assertEqual(
            SeriesStatus.DEVELOPMENT, insecure_policy.distroseries.status)
        self.assertTrue(insecure_policy.autoApprove(make_fake_upload()))
        self.assertTrue(insecure_policy.autoApprove(
            make_fake_upload(is_ppa=True)))

    def test_insecure_approves_proposed(self):
        # Uploads to the PROPOSED pocket of non-FROZEN distroseries are
        # approved by the insecure policy.
        insecure_policy = findPolicyByName("insecure")
        insecure_policy.setOptions(FakeOptions(distroseries="hoary-proposed"))
        self.assertEqual(
            SeriesStatus.DEVELOPMENT, insecure_policy.distroseries.status)
        self.assertTrue(insecure_policy.autoApprove(make_fake_upload()))

    def test_insecure_does_not_approve_proposed_post_release(self):
        # Uploads to the PROPOSED pocket are not auto-approved after
        # release.
        self.setHoaryStatus(SeriesStatus.CURRENT)
        insecure_policy = findPolicyByName("insecure")
        insecure_policy.setOptions(FakeOptions(distroseries="hoary-proposed"))
        self.assertFalse(insecure_policy.autoApprove(make_fake_upload()))

    def test_insecure_does_not_approve_frozen(self):
        # When the distroseries is FROZEN, uploads to the primary archive
        # wait in the UNAPPROVED queue, but PPA uploads are still approved.
        self.setHoaryStatus(SeriesStatus.FROZEN)
        insecure_policy = findPolicyByName("insecure")
        insecure_policy.setOptions(FakeOptions(distroseries="hoary-proposed"))
        self.assertFalse(insecure_policy.autoApprove(make_fake_upload()))
        self.assertTrue(insecure_policy.autoApprove(
            make_fake_upload(is_ppa=True)))

    def test_insecure_does_not_approve_updates(self):
        # Uploads to the UPDATES pocket are not auto-approved by the
        # insecure policy.  Despite not being allowed yet (see
        # UploadPolicy.checkUpload), PPA uploads to post-release pockets
        # would still be auto-approved.
        self.setHoaryStatus(SeriesStatus.CURRENT)
        insecure_policy = findPolicyByName("insecure")
        insecure_policy.setOptions(FakeOptions(distroseries="hoary-updates"))
        self.assertFalse(insecure_policy.autoApprove(make_fake_upload()))
        self.assertTrue(insecure_policy.autoApprove(
            make_fake_upload(is_ppa=True)))

    def test_buildd_does_not_approve_uefi(self):
        # Uploads to the primary archive containing UEFI custom files are
        # not approved.
        buildd_policy = findPolicyByName("buildd")
        uploadfile = CustomUploadFile(
            "uefi.tar.gz", None, 0, "main/raw-uefi", "extra", buildd_policy,
            None)
        upload = make_fake_upload(binaryful=True)
        upload.changes = FakeChangesFile(custom_files=[uploadfile])
        self.assertFalse(buildd_policy.autoApprove(upload))

    def test_buildd_approves_uefi_ppa(self):
        # Uploads to PPAs containing UEFI custom files are auto-approved.
        buildd_policy = findPolicyByName("buildd")
        uploadfile = CustomUploadFile(
            "uefi.tar.gz", None, 0, "main/raw-uefi", "extra", buildd_policy,
            None)
        upload = make_fake_upload(binaryful=True, is_ppa=True)
        upload.changes = FakeChangesFile(custom_files=[uploadfile])
        self.assertTrue(buildd_policy.autoApprove(upload))
