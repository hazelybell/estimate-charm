# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""SourcePackageRecipeBuild views."""

__metaclass__ = type

__all__ = [
    'SourcePackageRecipeBuildContextMenu',
    'SourcePackageRecipeBuildNavigation',
    'SourcePackageRecipeBuildView',
    'SourcePackageRecipeBuildCancelView',
    'SourcePackageRecipeBuildRescoreView',
    ]

from zope.interface import Interface
from zope.schema import Int

from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.buildmaster.enums import BuildStatus
from lp.code.interfaces.sourcepackagerecipebuild import (
    ISourcePackageRecipeBuild,
    )
from lp.services.job.interfaces.job import JobStatus
from lp.services.librarian.browser import FileNavigationMixin
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    ContextMenu,
    enabled_with_permission,
    LaunchpadView,
    Link,
    Navigation,
    )


UNEDITABLE_BUILD_STATES = (
    BuildStatus.FULLYBUILT,
    BuildStatus.FAILEDTOBUILD,
    BuildStatus.SUPERSEDED,
    BuildStatus.FAILEDTOUPLOAD,)


class SourcePackageRecipeBuildNavigation(Navigation, FileNavigationMixin):

    usedfor = ISourcePackageRecipeBuild


class SourcePackageRecipeBuildContextMenu(ContextMenu):
    """Navigation menu for sourcepackagerecipe build."""

    usedfor = ISourcePackageRecipeBuild

    facet = 'branches'

    links = ('cancel', 'rescore')

    @enabled_with_permission('launchpad.Admin')
    def cancel(self):
        if self.context.status in UNEDITABLE_BUILD_STATES:
            enabled = False
        else:
            enabled = True
        return Link('+cancel', 'Cancel build', icon='remove', enabled=enabled)

    @enabled_with_permission('launchpad.Admin')
    def rescore(self):
        if self.context.status in UNEDITABLE_BUILD_STATES:
            enabled = False
        else:
            enabled = True
        return Link('+rescore', 'Rescore build', icon='edit', enabled=enabled)


class SourcePackageRecipeBuildView(LaunchpadView):
    """Default view of a SourcePackageRecipeBuild."""

    @property
    def status(self):
        """A human-friendly status string."""
        if (self.context.status == BuildStatus.NEEDSBUILD
            and self.eta is None):
            return 'No suitable builders'
        return {
            BuildStatus.NEEDSBUILD: 'Pending build',
            BuildStatus.UPLOADING: 'Build uploading',
            BuildStatus.FULLYBUILT: 'Successful build',
            BuildStatus.MANUALDEPWAIT: (
                'Could not build because of missing dependencies'),
            BuildStatus.CHROOTWAIT: (
                'Could not build because of chroot problem'),
            BuildStatus.SUPERSEDED: (
                'Could not build because source package was superseded'),
            BuildStatus.FAILEDTOUPLOAD: 'Could not be uploaded correctly',
            }.get(self.context.status, self.context.status.title)

    @cachedproperty
    def eta(self):
        """The datetime when the build job is estimated to complete.

        This is the BuildQueue.estimated_duration plus the
        Job.date_started or BuildQueue.getEstimatedJobStartTime.
        """
        if self.context.buildqueue_record is None:
            return None
        queue_record = self.context.buildqueue_record
        if queue_record.job.status == JobStatus.WAITING:
            start_time = queue_record.getEstimatedJobStartTime()
            if start_time is None:
                return None
        else:
            start_time = queue_record.job.date_started
        duration = queue_record.estimated_duration
        return start_time + duration

    @cachedproperty
    def date(self):
        """The date when the build completed or is estimated to complete."""
        if self.estimate:
            return self.eta
        return self.context.date_finished

    @cachedproperty
    def estimate(self):
        """If true, the date value is an estimate."""
        if self.context.date_finished is not None:
            return False
        return self.eta is not None

    def binary_builds(self):
        return list(self.context.binary_builds)


class SourcePackageRecipeBuildCancelView(LaunchpadFormView):
    """View for cancelling a build."""

    class schema(Interface):
        """Schema for cancelling a build."""

    page_title = label = "Cancel build"

    @property
    def cancel_url(self):
        return canonical_url(self.context)
    next_url = cancel_url

    @action('Cancel build', name='cancel')
    def request_action(self, action, data):
        """Cancel the build."""
        self.context.cancelBuild()


class SourcePackageRecipeBuildRescoreView(LaunchpadFormView):
    """View for rescoring a build."""

    class schema(Interface):
        """Schema for deleting a build."""
        score = Int(
            title=u'Score', required=True,
            description=u'The score of the recipe.')

    page_title = label = "Rescore build"

    def __call__(self):
        if self.context.buildqueue_record is not None:
            return super(SourcePackageRecipeBuildRescoreView, self).__call__()
        self.request.response.addWarningNotification(
            'Cannot rescore this build because it is not queued.')
        self.request.response.redirect(canonical_url(self.context))

    @property
    def cancel_url(self):
        return canonical_url(self.context)
    next_url = cancel_url

    @action('Rescore build', name='rescore')
    def request_action(self, action, data):
        """Rescore the build."""
        self.context.buildqueue_record.lastscore = int(data['score'])

    @property
    def initial_values(self):
        return {'score': str(self.context.buildqueue_record.lastscore)}
