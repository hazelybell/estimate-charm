# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for sources list entries."""

from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.formlib.interfaces import IInputWidget
from zope.formlib.utility import setUpWidget
from zope.schema import Choice
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp import _
from lp.services.browser_helpers import get_user_agent_distroseries
from lp.services.propertycache import cachedproperty
from lp.services.webapp import LaunchpadView
from lp.soyuz.interfaces.archiveauthtoken import IArchiveAuthTokenSet


class SourcesListEntries:
    """For rendering sources.list entries.

    Represents a set of distroseries in a distribution archive.
    """

    def __init__(self, distribution, archive_url, valid_series):
        self.distribution = distribution
        self.archive_url = archive_url
        self.valid_series = valid_series


class SourcesListEntriesView(LaunchpadView):
    """Renders sources.list entries with a Javascript menu."""

    template = ViewPageTemplateFile('../templates/sources-list-entries.pt')

    def __init__(self, context, request, initially_without_selection=False,
        comment=None):
        self._initially_without_selection = initially_without_selection
        self.comment = comment
        super(SourcesListEntriesView, self).__init__(context, request)

    def initialize(self):
        self.terms = []
        for series in self.context.valid_series:
            distro_version = "%(series_name)s (%(series_version)s)" % {
                'series_name': series.displayname,
                'series_version': series.version
                }
            self.terms.append(SimpleTerm(series, series.name, distro_version))

        # If the call-site requested that the widget be displayed initially
        # without a selection, or we were not able to find a sensible
        # default series, then add an option to force the user to select
        # a distroseries.
        if self._initially_without_selection or self.default_series is None:
            initial_selection = "Choose your %s version" % (
                    self.context.distribution.displayname)
            self.terms.insert(0, SimpleTerm(
                None, self.initial_value_without_selection,
                initial_selection))

        field = Choice(__name__='series', title=_("Distro Series"),
                       vocabulary=SimpleVocabulary(self.terms), required=True)
        setUpWidget(self, 'series',  field, IInputWidget)
        self.series_widget.extra = "onChange='updateSeries(this);'"

    @property
    def initial_value_without_selection(self):
        return "YOUR_%s_VERSION_HERE" % (
            self.context.distribution.displayname.upper())

    @property
    def plain_series_widget(self):
        """Render a <select> control with no <div>s around it."""
        return self.series_widget.renderValue(self.default_series)

    @property
    def sources_in_more_than_one_series(self):
        """Whether this archive has sources in more than one distro series."""
        return len(self.terms) > 1

    @property
    def default_series(self):
        """Return the default series for this view."""
        # If we have not been provided with any valid distroseries, then
        # we return the currentseries of the distribution.
        if len(self.terms) == 0:
            return self.context.distribution.currentseries

        # If we only have one series then we have no choice...just return it.
        elif len(self.terms) == 1:
            return self.terms[0].value

        # If the caller has indicated that there should not be a default
        # distroseries selected then we return None.
        elif self._initially_without_selection:
            return None

        # Otherwise, if the request's user-agent includes the Ubuntu version
        # number, we check for a corresponding valid distroseries and, if one
        # is found, return it's name.
        version_number = get_user_agent_distroseries(
            self.request.getHeader('HTTP_USER_AGENT'))

        if version_number is not None:

            # Finally, check if this version is one of the available
            # distroseries for this archive:
            for term in self.terms:
                if (term.value is not None and
                    term.value.version == version_number):
                    return term.value

        # If we were not able to get the users distribution series, then
        # either they are running a different OS, or they are running a
        # very old version of Ubuntu, or they have explicitly tampered
        # with user-agent headers in their browser. In any case,
        # we won't try to guess a value, but instead force them to
        # select one.
        return None

    @property
    def default_series_name(self):
        """Return the name of the default series for this view."""
        series = self.default_series
        if series is not None:
            return series.name
        else:
            # Return the select value for the generic text noting to the
            # user that they should select a distroseries.
            return self.initial_value_without_selection


class SourcesListEntriesWidget:
    """Setup the sources list entries widget."""

    @cachedproperty
    def sources_list_entries(self):
        """Setup and return the sources list entries widget."""
        if self.active_token is None:
            entries = SourcesListEntries(
                self.archive.distribution, self.archive_url,
                self.archive.series_with_sources)
            return SourcesListEntriesView(entries, self.request)
        else:
            comment = "Personal access of %s (%s) to %s" % (
                self.sources_list_user.displayname,
                self.sources_list_user.name, self.archive.displayname)
            entries = SourcesListEntries(
                self.archive.distribution, self.active_token.archive_url,
                self.archive.series_with_sources)
            return SourcesListEntriesView(
                entries, self.request, comment=comment)

    @cachedproperty
    def active_token(self):
        """Return the corresponding current token for this subscription."""
        token_set = getUtility(IArchiveAuthTokenSet)
        return token_set.getActiveTokenForArchiveAndPerson(
            self.archive, self.sources_list_user)

    @property
    def archive_url(self):
        """Return an archive_url where available, or None."""
        if self.has_sources and not self.archive.is_copy:
            return self.archive.archive_url
        else:
            return None

    @cachedproperty
    def has_sources(self):
        """Whether or not this PPA has any sources for the view.

        This can be overridden by subclasses as necessary. It allows
        the view to determine whether to display "This PPA does not yet
        have any published sources" or "No sources matching 'blah'."
        """
        return not self.archive.getPublishedSources().is_empty()
