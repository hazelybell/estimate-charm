# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Policy management for the upload handler."""

__metaclass__ = type

__all__ = [
    "AbstractUploadPolicy",
    "ArchiveUploadType",
    "BuildDaemonUploadPolicy",
    "findPolicyByName",
    "IArchiveUploadPolicy",
    "UploadPolicyError",
    ]

from textwrap import dedent

from lazr.enum import (
    EnumeratedType,
    Item,
    )
from zope.component import (
    getGlobalSiteManager,
    getUtility,
    )
from zope.interface import (
    implements,
    Interface,
    )

from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.soyuz.enums import ArchivePurpose

# Number of seconds in an hour (used later)
HOURS = 3600


class UploadPolicyError(Exception):
    """Raised when a specific policy violation occurs."""


class IArchiveUploadPolicy(Interface):
    """The policy of an upload to a Launchpad archive.

    This is, in practice, just a marker interface for us to look up upload
    policies by name.

    If registered as a utility, any classes implementing this must be given as
    the 'component' argument of the <utility> directive so that a getUtility()
    call returns the class itself rather than an instance.  This is needed
    because the callsites usually change the policies (based on user-specified
    arguments).
    """


class ArchiveUploadType(EnumeratedType):

    SOURCE_ONLY = Item("Source only")
    BINARY_ONLY = Item("Binary only")
    MIXED_ONLY = Item("Mixed only")


class AbstractUploadPolicy:
    """Encapsulate the policy of an upload to a launchpad archive.

    An upload policy consists of a list of attributes which are used to
    verify an upload is permissible (e.g. whether or not there must be
    a valid signature on the .changes file). The policy also contains the
    tests themselves and they operate on NascentUpload instances in order
    to verify them.
    """
    implements(IArchiveUploadPolicy)

    name = 'abstract'
    options = None
    accepted_type = None  # Must be defined in subclasses.
    redirect_warning = None

    def __init__(self):
        """Prepare a policy..."""
        self.distro = None
        self.distroseries = None
        self.pocket = None
        self.archive = None
        self.unsigned_changes_ok = False
        self.unsigned_dsc_ok = False
        self.create_people = True
        # future_time_grace is in seconds. 28800 is 8 hours
        self.future_time_grace = 8 * HOURS
        # The earliest year we accept in a deb's file's mtime
        self.earliest_year = 1984

    def validateUploadType(self, upload):
        """Check that the type of the given upload is accepted by this policy.

        When the type (e.g. sourceful, binaryful or mixed) is not accepted,
        the upload is rejected.
        """
        if upload.sourceful and upload.binaryful:
            if self.accepted_type != ArchiveUploadType.MIXED_ONLY:
                upload.reject(
                    "Source/binary (i.e. mixed) uploads are not allowed.")

        elif upload.sourceful:
            if self.accepted_type != ArchiveUploadType.SOURCE_ONLY:
                upload.reject(
                    "Sourceful uploads are not accepted by this policy.")

        elif upload.binaryful:
            if self.accepted_type != ArchiveUploadType.BINARY_ONLY:
                message = dedent("""
                    Upload rejected because it contains binary packages.
                    Ensure you are using `debuild -S`, or an equivalent
                    command, to generate only the source package before
                    re-uploading.""")

                if upload.is_ppa:
                    message += dedent("""
                        See https://help.launchpad.net/Packaging/PPA for
                        more information.""")
                upload.reject(message)

        else:
            raise AssertionError(
                "Upload is not sourceful, binaryful or mixed.")

    def setOptions(self, options):
        """Store the options for later."""
        # Extract and locate the distribution though...
        self.distro = getUtility(IDistributionSet)[options.distro]
        if options.distroseries is not None:
            self.setDistroSeriesAndPocket(options.distroseries)

    def setDistroSeriesAndPocket(self, dr_name):
        """Set the distroseries and pocket from the provided name.

        It also sets self.archive to the distroseries main_archive.
        """
        if self.distroseries is not None:
            assert self.archive is not None, "Archive must be set."
            # We never override the policy
            return

        self.distroseriesname = dr_name
        self.distroseries, self.pocket = self.distro.getDistroSeriesAndPocket(
            dr_name, follow_aliases=True)

        if self.archive is None:
            self.archive = self.distroseries.main_archive

    def checkUpload(self, upload):
        """Mandatory policy checks on NascentUploads."""
        if self.archive.is_copy:
            if upload.sourceful:
                upload.reject(
                    "Source uploads to copy archives are not allowed.")
            elif upload.binaryful:
                # Buildd binary uploads (resulting from successful builds)
                # to copy archives may go into *any* pocket.
                return

        # reject PPA uploads by default
        self.rejectPPAUploads(upload)

        # execute policy specific checks
        self.policySpecificChecks(upload)

    def rejectPPAUploads(self, upload):
        """Reject uploads targeted to PPA.

        We will only allow it on 'insecure' and 'buildd' policy because we
        ensure the uploads are signed.
        """
        if upload.is_ppa:
            upload.reject(
                "PPA upload are not allowed in '%s' policy" % self.name)

    def policySpecificChecks(self, upload):
        """Implement any policy-specific checks in child."""
        raise NotImplementedError(
            "Policy specific checks must be implemented in child policies.")

    def autoApprove(self, upload):
        """Return whether the upload should be automatically approved.

        This is called only if the upload is a recognised package; if it
        is new, autoApproveNew is used instead.
        """
        # The base policy approves of everything.
        return True

    def autoApproveNew(self, upload):
        """Return whether the NEW upload should be automatically approved."""
        return False


class InsecureUploadPolicy(AbstractUploadPolicy):
    """The insecure upload policy is used by the poppy interface."""

    name = 'insecure'
    accepted_type = ArchiveUploadType.SOURCE_ONLY

    def setDistroSeriesAndPocket(self, dr_name):
        """Set the distroseries and pocket from the provided name.

        The insecure policy redirects uploads to a different pocket if
        Distribution.redirect_release_uploads is set.
        """
        super(InsecureUploadPolicy, self).setDistroSeriesAndPocket(dr_name)
        if (self.archive.purpose == ArchivePurpose.PRIMARY and
            self.distro.redirect_release_uploads and
            self.pocket == PackagePublishingPocket.RELEASE):
            self.pocket = PackagePublishingPocket.PROPOSED
            self.redirect_warning = "Redirecting %s to %s-proposed." % (
                self.distroseries, self.distroseries)

    def rejectPPAUploads(self, upload):
        """Insecure policy allows PPA upload."""
        return False

    def checkArchiveSizeQuota(self, upload):
        """Reject the upload if target archive size quota will be exceeded.

        This check will reject source upload exceeding the specified archive
        size quota.Binary upload will be skipped to avoid unnecessary hassle
        dealing with FAILEDTOUPLOAD builds.
        """
        # Skip the check for binary uploads or archives with no quota.
        if upload.binaryful or self.archive.authorized_size is None:
            return

        # Calculate the incoming upload total size.
        upload_size = 0
        for uploadfile in upload.changes.files:
            upload_size += uploadfile.size

        # All value in bytes.
        MEGA = 2 ** 20
        limit_size = self.archive.authorized_size * MEGA
        current_size = self.archive.estimated_size
        new_size = current_size + upload_size

        if new_size > limit_size:
            upload.reject(
                "PPA exceeded its size limit (%.2f of %.2f MiB). "
                "Ask a question in https://answers.launchpad.net/soyuz/ "
                "if you need more space." % (
                new_size / MEGA, self.archive.authorized_size))
        elif new_size > 0.95 * limit_size:
            # Warning users about a PPA over 95 % of the size limit.
            upload.warn(
                "PPA exceeded 95 %% of its size limit (%.2f of %.2f MiB). "
                "Ask a question in https://answers.launchpad.net/soyuz/ "
                "if you need more space." % (
                new_size / MEGA, self.archive.authorized_size))
        else:
            # No need to warn user about his PPA's size.
            pass

    def policySpecificChecks(self, upload):
        """The insecure policy does not allow SECURITY uploads for now.

        Also check if the upload is within the allowed quota.
        """
        self.checkArchiveSizeQuota(upload)
        # XXX cjwatson 2012-07-20 bug=1026665: For now, direct uploads
        # to SECURITY will not be built.  See
        # BuildPackageJob.postprocessCandidate.
        if self.pocket == PackagePublishingPocket.SECURITY:
            upload.reject(
                "This upload queue does not permit SECURITY uploads.")

    def autoApprove(self, upload):
        """The insecure policy auto-approves RELEASE/PROPOSED pocket stuff.

        PPA uploads are always auto-approved.
        RELEASE and PROPOSED pocket uploads (to main archives) are only
        auto-approved if the distroseries is in a non-FROZEN state
        pre-release.  (We already performed the IArchive.canModifySuite
        check in the checkUpload base method, which will deny RELEASE
        uploads post-release, but it doesn't hurt to repeat this for that
        case.)
        """
        if upload.is_ppa:
            return True

        auto_approve_pockets = (
            PackagePublishingPocket.RELEASE,
            PackagePublishingPocket.PROPOSED,
            )
        if self.pocket in auto_approve_pockets:
            if (self.distroseries.isUnstable() and
                self.distroseries.status != SeriesStatus.FROZEN):
                return True
        return False


class BuildDaemonUploadPolicy(AbstractUploadPolicy):
    """The build daemon upload policy is invoked by the slave scanner."""

    name = 'buildd'

    def __init__(self):
        super(BuildDaemonUploadPolicy, self).__init__()
        # We permit unsigned uploads because we trust our build daemons
        self.unsigned_changes_ok = True
        self.unsigned_dsc_ok = True

    def setOptions(self, options):
        """Store the options for later."""
        super(BuildDaemonUploadPolicy, self).setOptions(options)
        options.builds = True

    def policySpecificChecks(self, upload):
        """The buildd policy should enforce that the buildid matches."""
        # XXX: dsilvers 2005-10-14 bug=3135:
        # Implement this to check the buildid etc.
        pass

    def rejectPPAUploads(self, upload):
        """Buildd policy allows PPA upload."""
        return False

    def validateUploadType(self, upload):
        if upload.sourceful and upload.binaryful:
            if self.accepted_type != ArchiveUploadType.MIXED_ONLY:
                upload.reject(
                    "Source/binary (i.e. mixed) uploads are not allowed.")
        elif not upload.sourceful and not upload.binaryful:
            raise AssertionError(
                "Upload is not sourceful, binaryful or mixed.")

    def autoApprove(self, upload):
        """Check that all custom files in this upload can be auto-approved."""
        if upload.is_ppa:
            return True
        if upload.binaryful:
            for custom_file in upload.changes.custom_files:
                if not custom_file.autoApprove():
                    return False
        return True


class SyncUploadPolicy(AbstractUploadPolicy):
    """This policy is invoked when processing sync uploads."""

    name = 'sync'
    accepted_type = ArchiveUploadType.SOURCE_ONLY

    def __init__(self):
        AbstractUploadPolicy.__init__(self)
        # We don't require changes or dsc to be signed for syncs
        self.unsigned_changes_ok = True
        self.unsigned_dsc_ok = True

    def policySpecificChecks(self, upload):
        """Perform sync specific checks."""
        # XXX: dsilvers 2005-10-14 bug=3135:
        # Implement this to check the sync
        pass


def findPolicyByName(policy_name):
    """Return a new policy instance for the given policy name."""
    return getUtility(IArchiveUploadPolicy, policy_name)()


def register_archive_upload_policy_adapters():
    policies = [
        BuildDaemonUploadPolicy,
        InsecureUploadPolicy,
        SyncUploadPolicy]
    sm = getGlobalSiteManager()
    for policy in policies:
        sm.registerUtility(
            component=policy, provided=IArchiveUploadPolicy, name=policy.name)
