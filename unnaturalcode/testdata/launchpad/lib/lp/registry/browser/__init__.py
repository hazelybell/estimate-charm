# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Common registry browser helpers and mixins."""

__metaclass__ = type

__all__ = [
    'add_subscribe_link',
    'BaseRdfView',
    'get_status_counts',
    'MilestoneOverlayMixin',
    'RDFIndexView',
    'RegistryEditFormView',
    'RegistryDeleteViewMixin',
    'StatusCount',
    ]


from operator import attrgetter
import os

from storm.store import Store
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.browser.folder import ExportedFolder
from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    )
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.blueprints.model.specificationworkitem import SpecificationWorkItem
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.series import SeriesStatus
from lp.services.webapp.publisher import (
    canonical_url,
    DataDownloadView,
    LaunchpadView,
    )


class StatusCount:
    """A helper that stores the count of status for a list of items.

    Items such as `IBugTask` and `ISpecification` can be summarised by
    their status.
    """

    def __init__(self, status, count):
        """Set the status and count."""
        self.status = status
        self.count = count


def get_status_counts(workitems, status_attr, key='sortkey'):
    """Return a list StatusCounts summarising the workitem."""
    statuses = {}
    for workitem in workitems:
        status = getattr(workitem, status_attr)
        if status is None:
            # This is not something we want to count.
            continue
        if status not in statuses:
            statuses[status] = 0
        statuses[status] += 1
    return [
        StatusCount(status, statuses[status])
        for status in sorted(statuses, key=attrgetter(key))]


def add_subscribe_link(links):
    """Add the subscription-related links."""
    links.extend(['subscribe_to_bug_mail', 'edit_bug_mail'])


class MilestoneOverlayMixin:
    """A mixin that provides the data for the milestoneoverlay script."""

    milestone_can_release = True

    @property
    def milestone_form_uri(self):
        """URI for form displayed by the formoverlay widget."""
        return canonical_url(self.context) + '/+addmilestone/++form++'

    @property
    def series_api_uri(self):
        """The series URL for API access."""
        return canonical_url(self.context, path_only_if_possible=True)

    @property
    def milestone_table_class(self):
        """The milestone table will be hidden if there are no milestones."""
        if self.context.has_milestones:
            return 'listing'
        else:
            # The page can remove the 'hidden' class to make the table
            # visible.
            return 'listing hidden'

    @property
    def milestone_row_uri_template(self):
        if IProductSeries.providedBy(self.context):
            pillar = self.context.product
        else:
            pillar = self.context.distribution
        uri = canonical_url(pillar, path_only_if_possible=True)
        return '%s/+milestone/{name}/+productseries-table-row' % uri

    @property
    def register_milestone_script(self):
        """Return the script to enable milestone creation via AJAX."""
        uris = {
            'series_api_uri': self.series_api_uri,
            'milestone_form_uri': self.milestone_form_uri,
            'milestone_row_uri': self.milestone_row_uri_template,
            }
        return """
            LPJS.use(
                'node', 'lp.registry.milestoneoverlay',
                'lp.registry.milestonetable',
                function (Y) {

                var series_uri = '%(series_api_uri)s';
                var milestone_form_uri = '%(milestone_form_uri)s';
                var milestone_row_uri = '%(milestone_row_uri)s';
                var milestone_rows_id = '#milestone-rows';

                Y.on('domready', function () {
                    var create_milestone_link = Y.one(
                        '.menu-link-create_milestone');
                    create_milestone_link.addClass('js-action');
                    var milestone_table = Y.lp.registry.milestonetable;
                    var config = {
                        milestone_form_uri: milestone_form_uri,
                        series_uri: series_uri,
                        next_step: milestone_table.get_milestone_row,
                        activate_node: create_milestone_link
                        };
                    Y.lp.registry.milestoneoverlay.attach_widget(config);
                    var table_config = {
                        milestone_row_uri_template: milestone_row_uri,
                        milestone_rows_id: milestone_rows_id
                        }
                    Y.lp.registry.milestonetable.setup(table_config);
                });
            });
            """ % uris


class RegistryDeleteViewMixin:
    """A mixin class that provides common behavior for registry deletions."""

    @property
    def cancel_url(self):
        """The context's URL."""
        return canonical_url(self.context)

    def _getBugtasks(self, target, ignore_privacy=False):
        """Return the list `IBugTask`s associated with the target."""
        if IProductSeries.providedBy(target):
            params = BugTaskSearchParams(user=self.user)
            params.setProductSeries(target)
        else:
            params = BugTaskSearchParams(
                milestone=target, user=self.user,
                ignore_privacy=ignore_privacy)
        bugtasks = getUtility(IBugTaskSet).search(params)
        return list(bugtasks)

    def _getProductRelease(self, milestone):
        """The `IProductRelease` associated with the milestone."""
        return milestone.product_release

    def _getProductReleaseFiles(self, milestone):
        """The list of `IProductReleaseFile`s related to the milestone."""
        product_release = self._getProductRelease(milestone)
        if product_release is not None:
            return list(product_release.files)
        else:
            return []

    def _unsubscribe_structure(self, structure):
        """Removed the subscriptions from structure."""
        for subscription in structure.getSubscriptions():
            # The owner of the subscription or an admin are the only users
            # that can destroy a subscription, but this rule cannot prevent
            # the owner from removing the structure.
            subscription.delete()

    def _remove_series_bugs_and_specifications(self, series):
        """Untarget the associated bugs and specifications."""
        for spec in series.all_specifications:
            # The logged in user may have no permission to see the spec, so
            # make use of removeSecurityProxy to force it.
            removeSecurityProxy(spec).proposeGoal(None, self.user)
        for bugtask in self._getBugtasks(series):
            # Bugtasks cannot be deleted directly. In this case, the bugtask
            # is already reported on the product, so the series bugtask has
            # no purpose without a series.
            Store.of(bugtask).remove(bugtask)

    def _deleteProductSeries(self, series):
        """Remove the series and delete/unlink related objects.

        All subordinate milestones, releases, and files will be deleted.
        Milestone bugs and blueprints will be untargeted.
        Series bugs and blueprints will be untargeted.
        Series and milestone structural subscriptions are unsubscribed.
        Series branches are unlinked.
        """
        self._unsubscribe_structure(series)
        self._remove_series_bugs_and_specifications(series)
        series.branch = None

        for milestone in series.all_milestones:
            self._deleteMilestone(milestone)
        # Series are not deleted because some objects like translations are
        # problematic. The series is assigned to obsolete-junk. They must be
        # renamed to avoid name collision.
        date_time = series.datecreated.strftime('%Y%m%d-%H%M%S')
        series.name = '%s-%s-%s' % (
            series.product.name, series.name, date_time)
        series.status = SeriesStatus.OBSOLETE
        series.releasefileglob = None
        series.product = getUtility(ILaunchpadCelebrities).obsolete_junk

    def _deleteMilestone(self, milestone):
        """Delete a milestone and unlink related objects."""
        self._unsubscribe_structure(milestone)
        # We need to remove the milestone from every bug, even those the
        # current user can't see/change, otherwise we can't delete the
        # milestone, since it's still referenced.
        for bugtask in self._getBugtasks(milestone, ignore_privacy=True):
            nb = removeSecurityProxy(bugtask)
            if nb.conjoined_master is not None:
                Store.of(bugtask).remove(nb.conjoined_master)
            else:
                nb.milestone = None
        removeSecurityProxy(milestone.all_specifications).set(milestoneID=None)
        Store.of(milestone).find(
            SpecificationWorkItem, milestone_id=milestone.id).set(
                milestone_id=None)
        self._deleteRelease(milestone.product_release)
        milestone.destroySelf()

    def _deleteRelease(self, release):
        """Delete a release and it's files."""
        if release is not None:
            for release_file in release.files:
                release_file.destroySelf()
            release.destroySelf()


class RegistryEditFormView(LaunchpadEditFormView):
    """A base class that provides consistent edit form behaviour."""

    @property
    def page_title(self):
        """The page title."""
        return self.label

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    next_url = cancel_url

    @action("Change", name='change')
    def change_action(self, action, data):
        self.updateContextFromData(data)


class BaseRdfView(DataDownloadView):
    """A view that sets its mime-type to application/rdf+xml."""

    template = None
    filename = None

    content_type = 'application/rdf+xml'

    def getBody(self):
        """Render RDF output, and return it as a string encoded in UTF-8.

        Render the page template to produce RDF output.
        The return value is string data encoded in UTF-8.

        As a side-effect, HTTP headers are set for the mime type
        and filename for download."""
        unicodedata = self.template()
        encodeddata = unicodedata.encode('utf-8')
        return encodeddata


class RDFIndexView(LaunchpadView):
    """View for /rdf page."""
    page_title = label = "Launchpad RDF"


class RDFFolder(ExportedFolder):
    """Export the Launchpad RDF schemas."""
    folder = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), '../rdfspec/')
