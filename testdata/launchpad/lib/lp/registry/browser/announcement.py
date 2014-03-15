# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Announcement views."""

__metaclass__ = type

__all__ = [
    'AnnouncementAddView',
    'AnnouncementRetargetView',
    'AnnouncementPublishView',
    'AnnouncementRetractView',
    'AnnouncementDeleteView',
    'AnnouncementEditView',
    'AnnouncementSetView',
    'HasAnnouncementsView',
    'AnnouncementView',
    ]

from zope.interface import (
    implements,
    Interface,
    )
from zope.schema import (
    Choice,
    TextLine,
    )

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.validators.url import valid_webref
from lp.app.widgets.announcementdate import AnnouncementDateWidget
from lp.registry.interfaces.announcement import IAnnouncement
from lp.services.config import config
from lp.services.feeds.browser import (
    AnnouncementsFeedLink,
    FeedsMixin,
    RootAnnouncementsFeedLink,
    )
from lp.services.fields import (
    AnnouncementDate,
    Summary,
    Title,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.menu import (
    enabled_with_permission,
    Link,
    NavigationMenu,
    )
from lp.services.webapp.publisher import (
    canonical_url,
    LaunchpadView,
    )


class AnnouncementMenuMixin:
    """A mixin of links common to many menus."""

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        text = 'Modify announcement'
        return Link('+edit', text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def retarget(self):
        text = 'Move announcement'
        return Link('+retarget', text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def publish(self):
        text = 'Publish announcement'
        enabled = not self.context.published
        return Link('+publish', text, icon='edit', enabled=enabled)

    @enabled_with_permission('launchpad.Edit')
    def retract(self):
        text = 'Retract announcement'
        enabled = self.context.published
        return Link('+retract', text, icon='remove', enabled=enabled)

    @enabled_with_permission('launchpad.Edit')
    def delete(self):
        text = 'Delete announcement'
        return Link('+delete', text, icon='trash-icon')

    @enabled_with_permission('launchpad.Edit')
    def announce(self):
        text = 'Make announcement'
        summary = 'Create an item of news for this project'
        return Link('+announce', text, summary, icon='add')


class AnnouncementEditNavigationMenu(NavigationMenu, AnnouncementMenuMixin):
    """A sub-menu for different aspects of modifying an announcement."""

    usedfor = IAnnouncement
    facet = 'overview'
    title = 'Change announcement'
    links = ['edit', 'retarget', 'publish', 'retract', 'delete']


class IAnnouncementCreateMenu(Interface):
    """A marker interface for creation announcement navigation menu."""


class AnnouncementCreateNavigationMenu(NavigationMenu, AnnouncementMenuMixin):
    """A sub-menu for different aspects of modifying an announcement."""

    usedfor = IAnnouncementCreateMenu
    facet = 'overview'
    title = 'Create announcement'
    links = ['announce']


class AnnouncementFormMixin:
    """A mixin to provide the common form features."""

    @property
    def label(self):
        return self.context.title

    @property
    def cancel_url(self):
        """The announcements URL."""
        return canonical_url(self.context.target, view_name='+announcements')


class AddAnnouncementForm(Interface):
    """Form definition for the view which creates new Announcements."""

    title = Title(title=_('Headline'), required=True)
    summary = Summary(title=_('Summary'), required=True)
    url = TextLine(title=_('URL'), required=False, constraint=valid_webref,
        description=_("The web location of your announcement."))
    publication_date = AnnouncementDate(title=_('Date'), required=True)


class AnnouncementAddView(LaunchpadFormView):
    """A view for creating a new Announcement."""

    schema = AddAnnouncementForm
    label = "Make an announcement"
    page_title = label

    custom_widget('publication_date', AnnouncementDateWidget)

    @action(_('Make announcement'), name='announce')
    def announce_action(self, action, data):
        """Registers a new announcement."""
        self.context.announce(
            user=self.user,
            title=data.get('title'),
            summary=data.get('summary'),
            url=data.get('url'),
            publication_date=data.get('publication_date'))
        self.next_url = canonical_url(self.context)

    @property
    def action_url(self):
        return "%s/+announce" % canonical_url(self.context)

    @property
    def cancel_url(self):
        """The project's URL."""
        return canonical_url(self.context)


class AnnouncementEditView(AnnouncementFormMixin, LaunchpadFormView):
    """A view which allows you to edit the announcement."""

    schema = AddAnnouncementForm
    field_names = ['title', 'summary', 'url', ]
    page_title = 'Modify announcement'

    @property
    def initial_values(self):
        return {
            'title': self.context.title,
            'summary': self.context.summary,
            'url': self.context.url,
            }

    @action(_('Modify'), name='modify')
    def modify_action(self, action, data):
        self.context.modify(title=data.get('title'),
                            summary=data.get('summary'),
                            url=data.get('url'))
        self.next_url = canonical_url(self.context.target) + '/+announcements'


class AnnouncementRetargetForm(Interface):
    """Form that requires the user to choose a pillar for the Announcement."""

    target = Choice(
        title=_("For"),
        description=_("The project where this announcement is being made."),
        required=True, vocabulary='DistributionOrProductOrProjectGroup')


class AnnouncementRetargetView(AnnouncementFormMixin, LaunchpadFormView):
    """A view to move an annoucement to another project."""

    schema = AnnouncementRetargetForm
    field_names = ['target']
    page_title = 'Move announcement'

    def validate(self, data):
        """Ensure that the person can publish announcement at the new
        target.
        """

        target = data.get('target')

        if target is None:
            self.setFieldError('target',
                "There is no project with the name '%s'. "
                "Please check that name and try again." %
                self.request.form.get("field.target"))
            return

        if not check_permission('launchpad.Edit', target):
            self.setFieldError('target',
                "You don't have permission to make announcements for "
                "%s. Please check that name and try again." %
                target.displayname)
            return

    @action(_('Retarget'), name='retarget')
    def retarget_action(self, action, data):
        target = data.get('target')
        self.context.retarget(target)
        self.next_url = canonical_url(self.context.target) + '/+announcements'


class AnnouncementPublishView(AnnouncementFormMixin, LaunchpadFormView):
    """A view to publish an annoucement."""

    schema = AddAnnouncementForm
    field_names = ['publication_date']
    page_title = 'Publish announcement'

    custom_widget('publication_date', AnnouncementDateWidget)

    @action(_('Publish'), name='publish')
    def publish_action(self, action, data):
        publication_date = data['publication_date']
        self.context.setPublicationDate(publication_date)
        self.next_url = canonical_url(self.context.target) + '/+announcements'


class AnnouncementRetractView(AnnouncementFormMixin, LaunchpadFormView):
    """A view to unpublish an announcement."""

    schema = IAnnouncement
    page_title = 'Retract announcement'

    @action(_('Retract'), name='retract')
    def retract_action(self, action, data):
        self.context.retract()
        self.next_url = canonical_url(self.context.target) + '/+announcements'


class AnnouncementDeleteView(AnnouncementFormMixin, LaunchpadFormView):
    """A view to delete an annoucement."""

    schema = IAnnouncement
    page_title = 'Delete announcement'

    @action(_("Delete"), name="delete", validator='validate_cancel')
    def action_delete(self, action, data):
        self.context.destroySelf()
        self.next_url = canonical_url(self.context.target) + '/+announcements'


class HasAnnouncementsView(LaunchpadView, FeedsMixin):
    """A view class for pillars which have announcements."""
    implements(IAnnouncementCreateMenu)

    page_title = 'News and announcements'
    batch_size = config.launchpad.announcement_batch_size

    @cachedproperty
    def feed_url(self):
        if AnnouncementsFeedLink.usedfor.providedBy(self.context):
            return AnnouncementsFeedLink(self.context).href
        elif RootAnnouncementsFeedLink.usedfor.providedBy(self.context):
            return RootAnnouncementsFeedLink(self.context).href
        else:
            raise AssertionError("Unknown feed source")

    @cachedproperty
    def announcements(self):
        published_only = not check_permission('launchpad.Edit', self.context)
        return self.context.getAnnouncements(
                    limit=None, published_only=published_only)

    @cachedproperty
    def latest_announcements(self):
        published_only = not check_permission('launchpad.Edit', self.context)
        return list(self.context.getAnnouncements(
                    limit=5, published_only=published_only))

    @cachedproperty
    def has_announcements(self):
        return len(self.latest_announcements) > 0

    @cachedproperty
    def show_announcements(self):
        return (len(self.latest_announcements) > 0
            or check_permission('launchpad.Edit', self.context))

    @cachedproperty
    def announcement_nav(self):
        return BatchNavigator(
            self.announcements, self.request,
            size=self.batch_size)


class AnnouncementSetView(HasAnnouncementsView):
    """View a list of announcements.

    All other feed links should be disabled on this page by
    overriding the feed_types class variable.
    """
    feed_types = (
        AnnouncementsFeedLink,
        RootAnnouncementsFeedLink,
        )

    page_title = 'Announcements from all projects hosted in Launchpad'
    label = page_title


class AnnouncementView(LaunchpadView):
    """A view class for a single announcement."""

    @property
    def label(self):
        return self.context.title

    page_title = label
