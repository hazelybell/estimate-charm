# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for SourceListEntriesView."""

__metaclass__ = type
__all__ = [
    'TestDefaultSelectedSeries',
    'TestOneDistroSeriesOnly',
    'TestSourcesListComment',
    ]

from lp.services.webapp.servers import LaunchpadTestRequest
from lp.soyuz.browser.sourceslist import (
    SourcesListEntries,
    SourcesListEntriesView,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadFunctionalLayer


class TestDefaultSelectedSeries(TestCaseWithFactory):
    """Ensure that default selected series set from user-agent."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.distribution = self.factory.makeDistribution(
            name='ibuntu', displayname="Ibuntu")
        self.series = [
            self.factory.makeDistroSeries(name="feasty", version='9.04'),
            self.factory.makeDistroSeries(name="getsy", version='10.09'),
            self.factory.makeDistroSeries(name="ibix", version='11.04'),
        ]
        self.entries = SourcesListEntries(
            self.distribution, 'http://example.com/my/archive',
            self.series)

    def testDefaultToUserAgentSeries(self):
        # The distroseries version found in the user-agent header will
        # be selected by default.

        # Ubuntu version 10.09 in the user-agent should display as getsy
        view = SourcesListEntriesView(
            self.entries,
            LaunchpadTestRequest(
                HTTP_USER_AGENT='Mozilla/5.0 '
                                '(X11; U; Linux i686; en-US; rv:1.9.0.10) '
                                'Gecko/2009042523 Ubuntu/10.09 (whatever) '
                                'Firefox/3.0.10'))
        view.initialize()

        self.assertEqual(u'getsy', view.default_series_name)

        # Ubuntu version 9.04 in the user-agent should display as feasty
        view = SourcesListEntriesView(
            self.entries,
            LaunchpadTestRequest(
                HTTP_USER_AGENT='Mozilla/5.0 '
                                '(X11; U; Linux i686; en-US; rv:1.9.0.10) '
                                'Gecko/2009042523 Ubuntu/9.04 (whatever) '
                                'Firefox/3.0.10'))
        view.initialize()

        self.assertEqual(u'feasty', view.default_series_name)

    def testDefaultWithoutUserAgent(self):
        # If there is no user-agent setting, then we force the user
        # to make a selection.
        view = SourcesListEntriesView(self.entries, LaunchpadTestRequest())
        view.initialize()

        self.assertEqual('YOUR_IBUNTU_VERSION_HERE', view.default_series_name)

    def testNonRecognisedSeries(self):
        # If the supplied series in the user-agent is not recognized as a
        # valid distroseries for the distro, then we force the user
        # to make a selection.
        view = SourcesListEntriesView(self.entries, LaunchpadTestRequest(
                HTTP_USER_AGENT='Mozilla/5.0 '
                                '(X11; U; Linux i686; en-US; rv:1.9.0.10) '
                                'Gecko/2009042523 Ubuntu/12.04 (whatever) '
                                'Firefox/3.0.10'))

        view.initialize()

        self.assertEqual('YOUR_IBUNTU_VERSION_HERE', view.default_series_name)

    def testNonRecognisedDistro(self):
        # If the supplied series in the user-agent is not recognized as a
        # valid distroseries for the distro, then we force the user to
        # make a selection.
        view = SourcesListEntriesView(self.entries, LaunchpadTestRequest(
                HTTP_USER_AGENT='Mozilla/5.0 '
                                '(X11; U; Linux i686; en-US; rv:1.9.0.10) '
                                'Gecko/2009042523 Ubunti/9.04 (whatever) '
                                'Firefox/3.0.10'))

        view.initialize()

        self.assertEqual('YOUR_IBUNTU_VERSION_HERE', view.default_series_name)


class TestSourcesListComment(TestCaseWithFactory):
    """Ensure comment for sources.list entries displays appropriately"""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.distribution = self.factory.makeDistribution(name='ibuntu')
        self.series = [
            self.factory.makeDistroSeries(name="feasty", version='9.04'),
            ]
        self.entries = SourcesListEntries(
            self.distribution, 'http://example.com/my/archive',
            self.series)

    def testCommentDisplayedWhenProvided(self):
        # A comment provided to the constructor should appear when
        # rendered.
        my_comment = ("this comment should be displayed with the sources."
                      "list entries.")

        view = SourcesListEntriesView(
            self.entries, LaunchpadTestRequest(), comment=my_comment)
        view.initialize()

        html = view.__call__()
        self.assertTrue('#' + my_comment in html,
            "The comment was not included in the sources.list snippet.")


class TestOneDistroSeriesOnly(TestCaseWithFactory):
    """Ensure the correct behaviour when only one distro series is present.
    """
    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.distribution = self.factory.makeDistribution(name='ibuntu')

        # Ensure there is only one series available.
        self.series = [
            self.factory.makeDistroSeries(name="feasty", version='9.04'),
            ]
        self.entries = SourcesListEntries(
            self.distribution, 'http://example.com/my/archive',
            self.series)

        self.view = SourcesListEntriesView(
            self.entries, LaunchpadTestRequest())
        self.view.initialize()

    def testNoSelectorForOneSeries(self):
        # The selector should not be presented when there is only one series

        self.failUnless(self.view.sources_in_more_than_one_series is False)

    def testDefaultDistroSeries(self):
        # When there is only one distro series it should always be the
        # default.
        self.failUnless(self.view.default_series == self.series[0])
