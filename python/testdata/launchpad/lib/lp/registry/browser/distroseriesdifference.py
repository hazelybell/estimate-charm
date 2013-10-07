# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for DistroSeriesDifferences."""

__metaclass__ = type
__all__ = [
    'CommentXHTMLRepresentation',
    'DistroSeriesDifferenceView',
    ]

from lazr.restful.interfaces import IWebServiceClientRequest
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import (
    adapts,
    getUtility,
    )
from zope.formlib.itemswidgets import RadioWidget
from zope.interface import (
    implements,
    Interface,
    )
from zope.schema import Choice
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp.app.browser.launchpadform import (
    custom_widget,
    LaunchpadFormView,
    )
from lp.registry.enums import (
    DistroSeriesDifferenceStatus,
    DistroSeriesDifferenceType,
    )
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifference,
    )
from lp.registry.interfaces.distroseriesdifferencecomment import (
    IDistroSeriesDifferenceComment,
    IDistroSeriesDifferenceCommentSource,
    )
from lp.registry.model.distroseriesdifferencecomment import (
    DistroSeriesDifferenceComment,
    )
from lp.services.comments.browser.messagecomment import MessageComment
from lp.services.comments.interfaces.conversation import (
    IComment,
    IConversation,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    LaunchpadView,
    Navigation,
    stepthrough,
    )
from lp.services.webapp.authorization import check_permission


class DistroSeriesDifferenceNavigation(Navigation):
    usedfor = IDistroSeriesDifference

    @stepthrough('comments')
    def traverse_comment(self, id_str):
        try:
            id = int(id_str)
        except ValueError:
            return None

        return getUtility(
            IDistroSeriesDifferenceCommentSource).getForDifference(
                self.context, id)

    @property
    def parent_packagesets_names(self):
        """Return the formatted list of packagesets for the related
        sourcepackagename in the parent.
        """
        return self._formatPackageSets(self.context.parent_packagesets)

    @property
    def packagesets_names(self):
        """Return the formatted list of packagesets for the related
        sourcepackagename in the derived series.
        """
        return self._formatPackageSets(self.context.packagesets)

    def _formatPackageSets(self, packagesets):
        """Format a list of packagesets to display in the UI."""
        if packagesets is not None:
            return ', '.join([packageset.name for packageset in packagesets])
        else:
            return None


class IDistroSeriesDifferenceForm(Interface):
    """An interface used in the browser only for displaying form elements."""
    blacklist_options = Choice(vocabulary=SimpleVocabulary((
        SimpleTerm('NONE', 'NONE', 'No'),
        SimpleTerm(
            DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS,
            DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS.name,
            'All versions'),
        SimpleTerm(
            DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT,
            DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT.name,
            'These versions'),
        )))


class DistroSeriesDifferenceView(LaunchpadFormView):

    implements(IConversation)
    schema = IDistroSeriesDifferenceForm
    custom_widget('blacklist_options', RadioWidget)

    @property
    def initial_values(self):
        """Ensure the correct radio button is checked for blacklisting."""
        blacklisted_statuses = (
            DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT,
            DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS,
            )
        if self.context.status in blacklisted_statuses:
            return dict(blacklist_options=self.context.status)

        return dict(blacklist_options='NONE')

    @property
    def binary_summaries(self):
        """Return the summary of the related binary packages."""
        source_pub = None
        if self.context.source_pub is not None:
            source_pub = self.context.source_pub
        elif self.context.parent_source_pub is not None:
            source_pub = self.context.parent_source_pub

        if source_pub is not None:
            summary = source_pub.meta_sourcepackage.summary
            if summary:
                return summary.split('\n')

        return None

    @property
    def comments(self):
        """See `IConversation`."""
        comments = self.context.getComments().order_by(
            DistroSeriesDifferenceComment.id)
        return [
            DistroSeriesDifferenceDisplayComment(comment) for
                comment in comments]

    @cachedproperty
    def can_request_diffs(self):
        """Does the user have permission to request diff calculation?"""
        return check_permission('launchpad.Edit', self.context)

    @cachedproperty
    def show_add_comment(self):
        """Only show the 'Add comment' if an editor requests via JS."""
        return self.request.is_ajax and self.can_request_diffs

    @cachedproperty
    def enable_blacklist_options(self):
        """Should we enable the blacklisting (ignore) radio widget options.

        Only enable the options if an editor requests via JS and the user
        is an archive admin.
        """
        return self.request.is_ajax and check_permission(
            'launchpad.Admin', self.context)

    @cachedproperty
    def blacklist_options_css_class(self):
        """The css class for the blacklist option slot.
        'blacklist-options' if enabled.
        'blacklist-options-disabled' if not enabled.
        """
        if self.enable_blacklist_options:
            return 'blacklist-options'
        else:
            return 'blacklist-options-disabled'

    @property
    def display_diffs(self):
        """Only show diffs if there's a base version."""
        return self.context.base_version is not None

    @property
    def display_child_diff(self):
        """Only show the child diff if we need to."""
        return self.context.source_version != self.context.base_version

    @property
    def display_parent_diff(self):
        """Only show the parent diff if we need to."""
        return self.context.parent_source_version != self.context.base_version

    @property
    def can_have_packages_diffs(self):
        """Return whether this dsd could have packages diffs."""
        diff_versions = DistroSeriesDifferenceType.DIFFERENT_VERSIONS
        return self.context.difference_type == diff_versions

    @property
    def show_package_diffs_request_link(self):
        """Return whether package diffs can be requested.

        At least one of the package diffs for this dsd must be missing
        and the user must have lp.Edit.

        This method is used in the template to show the package diff
        request link.
        """
        derived_diff_computable = (
            not self.context.package_diff and self.display_child_diff)
        parent_diff_computable = (
            not self.context.parent_package_diff and self.display_parent_diff)
        return (self.display_diffs and
                self.can_request_diffs and
                (derived_diff_computable or
                 parent_diff_computable))

    @property
    def display_package_diffs_info(self):
        """Whether or not to show package differences info.

        Show if:

          There are no diffs yet available AND the base version is set AND
          either the parent or the derived version differs from the base
          version AND the user can request diff calculation,

        Or:

          There are diffs.

        """
        return (
            self.context.package_diff is not None or
            self.context.parent_package_diff is not None or
            self.show_package_diffs_request_link)


class IDistroSeriesDifferenceDisplayComment(IComment):
    """Marker interface."""


class DistroSeriesDifferenceDisplayComment(MessageComment):
    """Used simply to provide `IComment` for rendering."""
    implements(IDistroSeriesDifferenceDisplayComment)

    index = None

    download_url = None

    def __init__(self, comment):
        """Setup the attributes required by `IComment`."""
        super(DistroSeriesDifferenceDisplayComment, self).__init__(None)
        self.comment = comment


def get_message(comment):
    """Adapter from IDistroSeriesDifferenceDisplayComment to IMessage."""
    return comment.comment.message


class CommentXHTMLRepresentation(LaunchpadView):
    """Render individual comments when requested via the API."""
    adapts(IDistroSeriesDifferenceComment, IWebServiceClientRequest)
    implements(Interface)

    template = ViewPageTemplateFile(
        '../templates/distroseriesdifferencecomment-fragment.pt')

    @property
    def comment(self):
        return DistroSeriesDifferenceDisplayComment(self.context)
