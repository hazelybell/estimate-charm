# Copyright 2011-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `lp.registry.browser.distroseries`."""

__metaclass__ = type

from datetime import timedelta
import difflib
import re
from textwrap import TextWrapper
from urllib import urlencode
from urlparse import urlparse

from BeautifulSoup import BeautifulSoup
from fixtures import FakeLogger
from lazr.restful.interfaces import IJSONRequestCache
from lxml import html
import soupmatchers
from storm.zope.interfaces import IResultSet
from testtools.content import (
    Content,
    text_content,
    )
from testtools.content_type import UTF8_TEXT
from testtools.matchers import (
    EndsWith,
    Equals,
    LessThan,
    Not,
    )
from zope.component import getUtility
from zope.security.proxy import (
    ProxyFactory,
    removeSecurityProxy,
    )

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.archivepublisher.debversion import Version
from lp.registry.browser.distroseries import (
    ALL,
    HIGHER_VERSION_THAN_PARENT,
    NON_IGNORED,
    RESOLVED,
    seriesToVocab,
    )
from lp.registry.enums import (
    DistroSeriesDifferenceStatus,
    DistroSeriesDifferenceType,
    )
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import TeamMembershipPolicy
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import flush_database_caches
from lp.services.features.testing import FeatureFixture
from lp.services.propertycache import get_property_cache
from lp.services.utils import utc_now
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.escaping import html_escape
from lp.services.webapp.interaction import get_current_principal
from lp.services.webapp.interfaces import BrowserNotificationLevel
from lp.services.webapp.publisher import canonical_url
from lp.services.webapp.url import urlappend
from lp.soyuz.browser.archive import copy_asynchronously_message
from lp.soyuz.enums import (
    ArchivePermissionType,
    PackagePublishingStatus,
    SourcePackageFormat,
    )
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.distributionjob import (
    IDistroSeriesDifferenceJobSource,
    IInitializeDistroSeriesJobSource,
    )
from lp.soyuz.interfaces.packagecopyjob import IPlainPackageCopyJobSource
from lp.soyuz.interfaces.sourcepackageformat import (
    ISourcePackageFormatSelectionSet,
    )
from lp.soyuz.model.archivepermission import ArchivePermission
from lp.soyuz.model.packagecopyjob import PlainPackageCopyJob
from lp.soyuz.scripts.initialize_distroseries import InitializationError
from lp.testing import (
    ANONYMOUS,
    anonymous_logged_in,
    celebrity_logged_in,
    login,
    login_celebrity,
    login_person,
    normalize_whitespace,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    with_celebrity_logged_in,
    )
from lp.testing.dbuser import dbuser
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.matchers import (
    DocTestMatches,
    EqualsIgnoringWhitespace,
    HasQueryCount,
    )
from lp.testing.pages import (
    extract_text,
    find_tag_by_id,
    )
from lp.testing.views import create_initialized_view


class TestDistroSeriesView(TestCaseWithFactory):
    """Test the distroseries +index view."""

    layer = LaunchpadZopelessLayer

    def test_needs_linking(self):
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        distroseries = self.factory.makeDistroSeries(distribution=ubuntu)
        view = create_initialized_view(distroseries, '+index')
        self.assertEqual(view.needs_linking, None)

    def _createDifferenceAndGetView(self, difference_type, status=None):
        if status is None:
            status = DistroSeriesDifferenceStatus.NEEDS_ATTENTION
        # Helper function to create a valid DSD.
        dsp = self.factory.makeDistroSeriesParent()
        self.factory.makeDistroSeriesDifference(
            derived_series=dsp.derived_series,
            difference_type=difference_type, status=status)
        return create_initialized_view(dsp.derived_series, '+index')

    def test_num_version_differences_needing_attention(self):
        # num_version_differences_needing_attention counts
        # different-versions-type differences in needs-attention state.
        diff_type = DistroSeriesDifferenceType.DIFFERENT_VERSIONS
        view = self._createDifferenceAndGetView(diff_type)
        self.assertEqual(1, view.num_version_differences_needing_attention)

    def test_num_version_differences_needing_attention_limits_type(self):
        # num_version_differences_needing_attention ignores other types
        # of difference.
        diff_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        view = self._createDifferenceAndGetView(diff_type)
        self.assertEqual(0, view.num_version_differences_needing_attention)

    def test_num_version_differences_needing_attention_limits_status(self):
        # num_version_differences_needing_attention ignores differences
        # that do not need attention.
        diff_type = DistroSeriesDifferenceType.DIFFERENT_VERSIONS
        view = self._createDifferenceAndGetView(
            diff_type, status=DistroSeriesDifferenceStatus.RESOLVED)
        self.assertEqual(0, view.num_version_differences_needing_attention)

    def test_num_version_differences_counts_all_statuses(self):
        # num_version_differences counts DIFFERENT_VERSIONS differences
        # of all statuses.
        diff_type = DistroSeriesDifferenceType.DIFFERENT_VERSIONS
        series = self.factory.makeDistroSeriesParent().derived_series
        dsds = [
            self.factory.makeDistroSeriesDifference(
                series, difference_type=diff_type, status=status)
            for status in DistroSeriesDifferenceStatus.items]
        view = create_initialized_view(series, '+index')
        self.assertEqual(len(dsds), view.num_version_differences)

    def test_num_version_differences_ignores_limits_type(self):
        # num_version_differences ignores other types of difference.
        diff_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        view = self._createDifferenceAndGetView(diff_type)
        self.assertEqual(0, view.num_version_differences)

    def test_num_differences_in_parent(self):
        diff_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        view = self._createDifferenceAndGetView(diff_type)
        self.assertEqual(1, view.num_differences_in_parent)

    def test_num_differences_in_child(self):
        diff_type = DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES
        view = self._createDifferenceAndGetView(diff_type)
        self.assertEqual(1, view.num_differences_in_child)

    def test_wordVersionDifferences(self):
        diff_type = DistroSeriesDifferenceType.DIFFERENT_VERSIONS
        view = self._createDifferenceAndGetView(diff_type)
        self.assertEqual("1 package", view.wordVersionDifferences())

    def test_wordDifferencesInParent(self):
        diff_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        view = self._createDifferenceAndGetView(diff_type)
        self.assertEqual("1 package", view.wordDifferencesInParent())

    def test_wordDifferencesInChild(self):
        diff_type = DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES
        view = self._createDifferenceAndGetView(diff_type)
        self.assertEqual("1 package", view.wordDifferencesInChild())

    def test_alludeToParent_names_single_parent(self):
        dsp = self.factory.makeDistroSeriesParent()
        view = create_initialized_view(dsp.derived_series, '+index')
        self.assertEqual(dsp.parent_series.displayname, view.alludeToParent())

    def test_alludeToParent_refers_to_multiple_parents_collectively(self):
        dsp = self.factory.makeDistroSeriesParent()
        self.factory.makeDistroSeriesParent(derived_series=dsp.derived_series)
        view = create_initialized_view(dsp.derived_series, '+index')
        self.assertEqual("a parent series", view.alludeToParent())

    def test_link_to_version_diffs_needing_attention(self):
        diff_type = DistroSeriesDifferenceType.DIFFERENT_VERSIONS
        view = self._createDifferenceAndGetView(diff_type)
        link = view.link_to_version_diffs_needing_attention
        self.assertThat(link, EndsWith('/+localpackagediffs'))

    def test_link_to_all_version_diffs(self):
        diff_type = DistroSeriesDifferenceType.DIFFERENT_VERSIONS
        view = self._createDifferenceAndGetView(diff_type)
        link = view.link_to_all_version_diffs
        self.assertIn('/+localpackagediffs?', link)

    def test_link_to_differences_in_parent(self):
        diff_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        view = self._createDifferenceAndGetView(diff_type)
        link = view.link_to_differences_in_parent
        self.assertThat(link, EndsWith('/+missingpackages'))

    def test_link_to_differences_in_child(self):
        diff_type = DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES
        view = self._createDifferenceAndGetView(diff_type)
        link = view.link_to_differences_in_child
        self.assertThat(link, EndsWith('/+uniquepackages'))


class DistroSeriesIndexFunctionalTestCase(TestCaseWithFactory):
    """Test the distroseries +index page."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(DistroSeriesIndexFunctionalTestCase, self).setUp()
        # Use a FakeLogger fixture to prevent Memcached warnings to be
        # printed to stdout while browsing pages.
        self.useFixture(FakeLogger())

    def _setupDifferences(self, name, parent_names, nb_diff_versions,
                          nb_diff_child, nb_diff_parent):
        # Helper to create DSDs of the different types.
        derived_series = self.factory.makeDistroSeries(name=name)
        self.simple_user = self.factory.makePerson()
        # parent_names can be a list of parent names or a single name
        # for a single parent (e.g. ['parent1_name', 'parent2_name'] or
        # 'parent_name').
        # If multiple parents are created, the DSDs will be created with
        # the first one.
        if type(parent_names) == str:
            parent_names = [parent_names]
        dsps = []
        for parent_name in parent_names:
            parent_series = self.factory.makeDistroSeries(name=parent_name)
            dsps.append(self.factory.makeDistroSeriesParent(
                derived_series=derived_series, parent_series=parent_series))
        first_parent_series = dsps[0].parent_series
        for i in range(nb_diff_versions):
            diff_type = DistroSeriesDifferenceType.DIFFERENT_VERSIONS
            self.factory.makeDistroSeriesDifference(
                derived_series=derived_series,
                difference_type=diff_type,
                parent_series=first_parent_series)
        for i in range(nb_diff_child):
            diff_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
            self.factory.makeDistroSeriesDifference(
                derived_series=derived_series,
                difference_type=diff_type,
                parent_series=first_parent_series)
        for i in range(nb_diff_parent):
            diff_type = DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES
            self.factory.makeDistroSeriesDifference(
                derived_series=derived_series,
                difference_type=diff_type,
                parent_series=first_parent_series)
        return derived_series

    def test_differences_portlet_all_differences(self):
        # The difference portlet shows the differences with the parent
        # series.
        derived_series = self._setupDifferences('deri', 'sid', 1, 2, 3)
        portlet_display = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Derivation portlet header', 'h2',
                text='Derived from Sid'))

        with person_logged_in(self.simple_user):
            view = create_initialized_view(
                derived_series,
                '+index',
                principal=self.simple_user)
            html_content = view()

        self.assertThat(html_content, portlet_display)

    def test_differences_portlet_all_differences_multiple_parents(self):
        # The difference portlet shows the differences with the multiple
        # parent series.
        derived_series = self._setupDifferences(
            'deri', ['sid1', 'sid2'], 0, 1, 0)
        portlet_display = soupmatchers.HTMLContains(soupmatchers.Tag(
            'Derivation portlet header', 'h2',
            text='Derived from 2 parents'))

        with person_logged_in(self.simple_user):
            view = create_initialized_view(
                derived_series,
                '+index',
                principal=self.simple_user)
            html_text = view()

        self.assertThat(html_text, portlet_display)

    def test_differences_portlet_no_differences(self):
        # The difference portlet displays 'No differences' if there is no
        # differences with the parent.
        derived_series = self._setupDifferences('deri', 'sid', 0, 0, 0)
        portlet_display = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Derivation portlet header', 'h2',
                text='Derived from Sid'),
            soupmatchers.Tag(
                'Child diffs link', True,
                text=re.compile('\s*No differences\s*')),
              )

        with person_logged_in(self.simple_user):
            view = create_initialized_view(
                derived_series,
                '+index',
                principal=self.simple_user)
            html_content = view()

        self.assertThat(html_content, portlet_display)

    def test_differences_portlet_initializing(self):
        # The difference portlet displays 'The series is initializing.' if
        # there is an initializing job for the series.
        derived_series = self.factory.makeDistroSeries()
        parent_series = self.factory.makeDistroSeries()
        self.simple_user = self.factory.makePerson()
        job_source = getUtility(IInitializeDistroSeriesJobSource)
        job_source.create(derived_series, [parent_series.id])
        portlet_display = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Derived series', 'h2',
                text='Series initialization in progress'),
            soupmatchers.Tag(
                'Init message', True,
                text=re.compile('\s*This series is initializing.\s*')),
              )

        with person_logged_in(self.simple_user):
            view = create_initialized_view(
                derived_series,
                '+index',
                principal=self.simple_user)
            html_content = view()

        self.assertTrue(derived_series.isInitializing())
        self.assertThat(html_content, portlet_display)

    def test_differences_portlet_initialization_failed(self):
        # The difference portlet displays a failure message if initialization
        # for the series has failed.
        derived_series = self.factory.makeDistroSeries()
        parent_series = self.factory.makeDistroSeries()
        self.simple_user = self.factory.makePerson()
        job_source = getUtility(IInitializeDistroSeriesJobSource)
        job = job_source.create(derived_series, [parent_series.id])
        job.start()
        job.fail()
        portlet_display = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Derived series', 'h2',
                text='Series initialization has failed'),
            )
        with person_logged_in(self.simple_user):
            view = create_initialized_view(
                derived_series, '+index', principal=self.simple_user)
            html_content = view()
        self.assertThat(html_content, portlet_display)

    def assertInitSeriesLinkPresent(self, series, person):
        self._assertInitSeriesLink(series, person, True)

    def assertInitSeriesLinkNotPresent(self, series, person):
        self._assertInitSeriesLink(series, person, False)

    def _assertInitSeriesLink(self, series, person, present=True):
        # Helper method to check the presence/absence of the link to
        # +initseries.
        if person == 'admin':
            person = getUtility(ILaunchpadCelebrities).admin.teamowner

        init_link_matcher = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Initialize series', 'a',
                text='Initialize series',
                attrs={'href': '%s/+initseries' % canonical_url(series)}))

        with person_logged_in(person):
            view = create_initialized_view(
                series,
                '+index',
                principal=person)
            html_content = view()

        if present:
            self.assertThat(html_content, init_link_matcher)
        else:
            self.assertThat(html_content, Not(init_link_matcher))

    def test_differences_init_link_admin(self):
        # The link to +initseries is displayed to admin users.
        series = self.factory.makeDistroSeries()

        self.assertInitSeriesLinkPresent(series, 'admin')

    def test_differences_init_link_series_driver(self):
        # The link to +initseries is displayed to the distroseries's
        # drivers.
        distroseries = self.factory.makeDistroSeries()
        driver = self.factory.makePerson()
        with celebrity_logged_in('admin'):
            distroseries.driver = driver

        self.assertInitSeriesLinkPresent(distroseries, driver)

    def test_differences_init_link_not_admin(self):
        # The link to +initseries is not displayed to not admin users if the
        # feature flag is enabled.
        series = self.factory.makeDistroSeries()
        person = self.factory.makePerson()

        self.assertInitSeriesLinkNotPresent(series, person)

    def test_differences_init_link_initialized(self):
        # The link to +initseries is not displayed if the series is
        # already initialized (i.e. has any published package).
        series = self.factory.makeDistroSeries()
        self.factory.makeSourcePackagePublishingHistory(
            archive=series.main_archive,
            distroseries=series)

        self.assertInitSeriesLinkNotPresent(series, 'admin')

    def test_differences_init_link_series_initializing(self):
        # The link to +initseries is not displayed if the series is
        # initializing.
        series = self.factory.makeDistroSeries()
        parent_series = self.factory.makeDistroSeries()
        job_source = getUtility(IInitializeDistroSeriesJobSource)
        job_source.create(series, [parent_series.id])

        self.assertInitSeriesLinkNotPresent(series, 'admin')


class TestDistroSeriesDerivationPortlet(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    @property
    def job_source(self):
        return getUtility(IInitializeDistroSeriesJobSource)

    def test_initialization_failed_can_retry(self):
        # When initialization has failed and the user has the ability to retry
        # it prompts the user to try again.
        series = self.factory.makeDistroSeries()
        parent = self.factory.makeDistroSeries()
        job = self.job_source.create(series, [parent.id])
        job.start()
        job.fail()
        with person_logged_in(series.owner):
            view = create_initialized_view(series, '+portlet-derivation')
            html_content = view()
        self.assertThat(
            extract_text(html_content), DocTestMatches(
                "Series initialization has failed\n"
                "You can attempt initialization again."))

    def test_initialization_failed_cannot_retry(self):
        # When initialization has failed and the user does not have the
        # ability to retry it suggests contacting someone who can.
        series = self.factory.makeDistroSeries()
        parent = self.factory.makeDistroSeries()
        job = self.job_source.create(series, [parent.id])
        job.start()
        job.fail()
        with person_logged_in(series.distribution.owner):
            series.distribution.owner.displayname = u"Bob Individual"
        with anonymous_logged_in():
            view = create_initialized_view(series, '+portlet-derivation')
            html_content = view()
        self.assertThat(
            extract_text(html_content), DocTestMatches(
                "Series initialization has failed\n"
                "You cannot attempt initialization again, "
                "but Bob Individual may be able to help."))
        # When the owner is a team the message differs slightly from when the
        # owner is an individual.
        with person_logged_in(series.distribution.owner):
            series.distribution.owner = self.factory.makeTeam(
                displayname=u"Team Teamy Team Team",
                membership_policy=TeamMembershipPolicy.RESTRICTED)
        with anonymous_logged_in():
            view = create_initialized_view(series, '+portlet-derivation')
            html_content = view()
        self.assertThat(
            extract_text(html_content), DocTestMatches(
                "Series initialization has failed\n"
                "You cannot attempt initialization again, but a "
                "member of Team Teamy Team Team may be able to help."))

    def load_afresh(self, thing):
        naked_thing = removeSecurityProxy(thing)
        naked_thing = IStore(naked_thing.__class__).get(
            naked_thing.__class__, naked_thing.id)
        return ProxyFactory(naked_thing)

    def fail_job_with_error(self, job, error):
        # We need to switch to the initializedistroseries user to set the
        # error_description on the given job. Which is a PITA.
        distroseries = job.distroseries
        with dbuser("initializedistroseries"):
            job = self.job_source.get(distroseries)
            job.start()
            job.fail()
            job.notifyUserError(error)

    def test_initialization_failure_explanation_shown(self):
        # When initialization has failed an explanation of the failure can be
        # displayed. It depends on the nature of the failure; only some error
        # types are displayed.
        series = self.factory.makeDistroSeries()
        parent = self.factory.makeDistroSeries()
        job = self.job_source.create(series, [parent.id])
        self.fail_job_with_error(
            job, InitializationError(
                "You cannot be serious. That's really going "
                "to hurt. Put it away."))
        # Load series again because the connection was closed in
        # fail_job_with_error().
        series = self.load_afresh(series)
        with person_logged_in(series.owner):
            view = create_initialized_view(series, '+portlet-derivation')
            html_content = view()
        self.assertThat(
            extract_text(html_content), DocTestMatches(
                "Series initialization has failed\n"
                "You cannot be serious. That's really going "
                "to hurt. Put it away.\n"
                "You can attempt initialization again."))


class TestMilestoneBatchNavigatorAttribute(TestCaseWithFactory):
    """Test the series.milestone_batch_navigator attribute."""

    layer = LaunchpadZopelessLayer

    def test_distroseries_milestone_batch_navigator(self):
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        distroseries = self.factory.makeDistroSeries(distribution=ubuntu)
        for name in ('a', 'b', 'c', 'd'):
            distroseries.newMilestone(name)
        view = create_initialized_view(distroseries, name='+index')
        self._check_milestone_batch_navigator(view)

    def test_productseries_milestone_batch_navigator(self):
        product = self.factory.makeProduct()
        for name in ('a', 'b', 'c', 'd'):
            product.development_focus.newMilestone(name)

        view = create_initialized_view(
            product.development_focus, name='+index')
        self._check_milestone_batch_navigator(view)

    def _check_milestone_batch_navigator(self, view):
        config.push('default-batch-size', """
        [launchpad]
        default_batch_size: 2
        """)
        self.assert_(
            isinstance(view.milestone_batch_navigator, BatchNavigator),
            'milestone_batch_navigator is not a BatchNavigator object: %r'
            % view.milestone_batch_navigator)
        self.assertEqual(4, view.milestone_batch_navigator.batch.total())
        expected = [
            'd',
            'c',
            ]
        milestone_names = [
            item.name
            for item in view.milestone_batch_navigator.currentBatch()]
        self.assertEqual(expected, milestone_names)
        config.pop('default-batch-size')


class TestDistroSeriesAddView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistroSeriesAddView, self).setUp()
        self.user = self.factory.makePerson()
        self.distribution = self.factory.makeDistribution(owner=self.user)

    def createNewDistroseries(self):
        form = {
            "field.name": u"polished",
            "field.version": u"12.04",
            "field.displayname": u"Polished Polecat",
            "field.summary": u"Even The Register likes it.",
            "field.actions.create": u"Add Series",
            }
        with person_logged_in(self.user):
            create_initialized_view(self.distribution, "+addseries",
                                    form=form)
        distroseries = self.distribution.getSeries(u"polished")
        return distroseries

    def assertCreated(self, distroseries):
        self.assertEqual(u"polished", distroseries.name)
        self.assertEqual(u"12.04", distroseries.version)
        self.assertEqual(u"Polished Polecat", distroseries.displayname)
        self.assertEqual(u"Polished Polecat", distroseries.title)
        self.assertEqual(u"Even The Register likes it.", distroseries.summary)
        self.assertEqual(u"", distroseries.description)
        self.assertEqual(self.user, distroseries.owner)

    def test_plain_submit(self):
        # When creating a new DistroSeries via DistroSeriesAddView, the title
        # is set to the same as the displayname (title is, in any case,
        # deprecated), the description is left empty, and previous_series is
        # None (DistroSeriesInitializeView takes care of setting that).
        distroseries = self.createNewDistroseries()
        self.assertCreated(distroseries)
        self.assertIs(None, distroseries.previous_series)

    def test_submit_sets_previous_series(self):
        # Creating a new series when one already exists should set the
        # previous_series.
        old_series = self.factory.makeDistroSeries(
            self.distribution, version='11.10')
        # A yet older series.
        self.factory.makeDistroSeries(
            self.distribution, version='11.04')
        old_time = utc_now() - timedelta(days=5)
        removeSecurityProxy(old_series).datereleased = old_time
        distroseries = self.createNewDistroseries()
        self.assertEqual(old_series, distroseries.previous_series)


class TestDistroSeriesInitializeView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_init(self):
        # There exists a +initseries view for distroseries.
        distroseries = self.factory.makeDistroSeries()
        view = create_initialized_view(distroseries, "+initseries")
        self.assertTrue(view)

    def test_form_shown(self):
        # The form is shown.
        distroseries = self.factory.makeDistroSeries()
        view = create_initialized_view(distroseries, "+initseries")
        root = html.fromstring(view())
        self.assertNotEqual([], root.cssselect("#initseries-form-container"))
        # A different explanatory message is shown for clients that don't
        # process Javascript.
        [message] = root.cssselect("p.error.message")
        self.assertIn(
            u"Javascript is required to use this page",
            message.text)
        self.assertIn(
            u"javascript-disabled",
            message.get("class").split())

    def test_seriesToVocab(self):
        distroseries = self.factory.makeDistroSeries()
        formatted_dict = seriesToVocab(distroseries)

        self.assertEquals(
            ['api_uri', 'title', 'value'],
            sorted(formatted_dict.keys()))

    def test_is_first_derivation(self):
        # If the distro has no initialized series, this initialization
        # is a 'first_derivation'.
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeDistroSeries(
            distribution=distroseries.distribution)
        view = create_initialized_view(distroseries, "+initseries")
        cache = IJSONRequestCache(view.request).objects

        self.assertTrue(cache['is_first_derivation'])

    def test_not_is_first_derivation(self):
        # If the distro has an initialized series, this initialization
        # is not a 'first_derivation'. The previous_series and the
        # previous_series' parents are in LP.cache to be used by
        # Javascript on the +initseries page.
        previous_series = self.factory.makeDistroSeries()
        previous_parent1 = self.factory.makeDistroSeriesParent(
            derived_series=previous_series).parent_series
        previous_parent2 = self.factory.makeDistroSeriesParent(
            derived_series=previous_series).parent_series
        distroseries = self.factory.makeDistroSeries(
            previous_series=previous_series)
        another_distroseries = self.factory.makeDistroSeries(
            distribution=distroseries.distribution)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=another_distroseries)
        view = create_initialized_view(distroseries, "+initseries")
        cache = IJSONRequestCache(view.request).objects

        self.assertFalse(cache['is_first_derivation'])
        self.assertContentEqual(
            seriesToVocab(previous_series),
            cache['previous_series'])
        self.assertEqual(
            2,
            len(cache['previous_parents']))
        self.assertContentEqual(
            seriesToVocab(previous_parent1),
            cache['previous_parents'][0])
        self.assertContentEqual(
            seriesToVocab(previous_parent2),
            cache['previous_parents'][1])

    def test_form_hidden_when_distroseries_is_initialized(self):
        # The form is hidden when the series has already been initialized.
        distroseries = self.factory.makeDistroSeries(
            previous_series=self.factory.makeDistroSeries())
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries, archive=distroseries.main_archive)
        view = create_initialized_view(distroseries, "+initseries")
        root = html.fromstring(view())
        self.assertEqual([], root.cssselect("#initseries-form-container"))
        # Instead an explanatory message is shown.
        [message] = root.cssselect("p.error.message")
        self.assertThat(
            message.text, EqualsIgnoringWhitespace(
                u"This series already contains source packages "
                u"and cannot be initialized again."))

    def test_form_hidden_when_distroseries_is_being_initialized(self):
        # The form is hidden when the series has already been derived.
        distroseries = self.factory.makeDistroSeries()
        getUtility(IInitializeDistroSeriesJobSource).create(
            distroseries, [self.factory.makeDistroSeries().id])
        view = create_initialized_view(distroseries, "+initseries")
        root = html.fromstring(view())
        self.assertEqual([], root.cssselect("#initseries-form-container"))
        # Instead an explanatory message is shown.
        [message] = root.cssselect("p.error.message")
        self.assertThat(
            message.text, EqualsIgnoringWhitespace(
                u"This series is already being initialized."))

    def test_form_hidden_when_previous_series_none(self):
        # If the distribution has an initialized series and the
        # distroseries' previous_series is None: the form is hidden and
        # the page contains an error message.
        distroseries = self.factory.makeDistroSeries(
            previous_series=None)
        another_distroseries = self.factory.makeDistroSeries(
            distribution=distroseries.distribution)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=another_distroseries)
        view = create_initialized_view(distroseries, "+initseries")
        root = html.fromstring(view())
        self.assertEqual([], root.cssselect("#initseries-form-container"))
        # Instead an explanatory message is shown.
        [message] = root.cssselect("p.error.message")
        self.assertThat(
            message.text, EqualsIgnoringWhitespace(
                u'Unable to initialize series: the distribution '
                u'already has initialized series and this distroseries '
                u'has no previous series.'))

    def test_form_hidden_when_no_publisher_config_set_up(self):
        # If the distribution has no publisher config set up:
        # the form is hidden and the page contains an error message.
        distribution = self.factory.makeDistribution(
            no_pubconf=True, name="distro")
        distroseries = self.factory.makeDistroSeries(
            distribution=distribution)
        view = create_initialized_view(distroseries, "+initseries")
        root = html.fromstring(view())
        self.assertEqual([], root.cssselect("#initseries-form-container"))
        # Instead an explanatory message is shown.
        [message] = root.cssselect("p.error.message")
        self.assertThat(
            message.text, EqualsIgnoringWhitespace(
                u"The series' distribution has no publisher configuration. "
                u"Please ask an administrator to set this up."))


class TestDistroSeriesInitializeViewAccess(TestCaseWithFactory):
    """Test access to IDS.+initseries."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestDistroSeriesInitializeViewAccess,
              self).setUp('foo.bar@canonical.com')

    def test_initseries_access_anon(self):
        # Anonymous users cannot access +initseries.
        distroseries = self.factory.makeDistroSeries()
        view = create_initialized_view(distroseries, "+initseries")
        login(ANONYMOUS)

        self.assertEqual(
            False,
            check_permission('launchpad.Edit', view))

    def test_initseries_access_simpleuser(self):
        # Unprivileged users cannot access +initseries.
        distroseries = self.factory.makeDistroSeries()
        view = create_initialized_view(distroseries, "+initseries")
        login_person(self.factory.makePerson())

        self.assertEqual(
            False,
            check_permission('launchpad.Edit', view))

    def test_initseries_access_admin(self):
        # Users with lp.Admin can access +initseries.
        distroseries = self.factory.makeDistroSeries()
        view = create_initialized_view(distroseries, "+initseries")
        login_celebrity('admin')

        self.assertEqual(
            True,
            check_permission('launchpad.Edit', view))

    def test_initseries_access_driver(self):
        # Distroseries drivers can access +initseries.
        distroseries = self.factory.makeDistroSeries()
        view = create_initialized_view(distroseries, "+initseries")
        driver = self.factory.makePerson()
        with celebrity_logged_in('admin'):
            distroseries.driver = driver
        login_person(driver)

        self.assertEqual(
            True,
            check_permission('launchpad.Edit', view))


class DistroSeriesDifferenceMixin:
    """A helper class for testing differences pages"""

    def _test_packagesets(self, html_content, packageset_text,
                          packageset_class, msg_text):
        parent_packagesets = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                msg_text, 'td',
                attrs={'class': packageset_class},
                text=packageset_text))

        self.assertThat(html_content, parent_packagesets)

    def _createChildAndParent(self):
        derived_series = self.factory.makeDistroSeries(name='derilucid')
        parent_series = self.factory.makeDistroSeries(name='lucid')
        self.factory.makeDistroSeriesParent(
            derived_series=derived_series, parent_series=parent_series)
        return (derived_series, parent_series)

    def _createChildAndParents(self, other_parent_series=None):
        derived_series, parent_series = self._createChildAndParent()
        self.factory.makeDistroSeriesParent(
            derived_series=derived_series, parent_series=other_parent_series)
        return (derived_series, parent_series)


class TestDistroSeriesLocalDiffPerformance(TestCaseWithFactory,
                                           DistroSeriesDifferenceMixin):
    """Test the distroseries +localpackagediffs page's performance."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistroSeriesLocalDiffPerformance,
             self).setUp('foo.bar@canonical.com')
        self.simple_user = self.factory.makePerson()

    def _assertQueryCount(self, derived_series):
        # With no DistroSeriesDifferences the query count should be low and
        # fairly static. However, with some DistroSeriesDifferences the query
        # count will be higher, but it should remain the same no matter how
        # many differences there are.
        ArchivePermission(
            archive=derived_series.main_archive, person=self.simple_user,
            component=getUtility(IComponentSet)["main"],
            permission=ArchivePermissionType.QUEUE_ADMIN)
        login_person(self.simple_user)

        def add_differences(num):
            for index in xrange(num):
                version = self.factory.getUniqueInteger()
                versions = {
                    'base': u'1.%d' % version,
                    'derived': u'1.%dderived1' % version,
                    'parent': u'1.%d-1' % version,
                    }
                dsd = self.factory.makeDistroSeriesDifference(
                    derived_series=derived_series,
                    versions=versions)

                # Push a base_version in... not sure how better to do it.
                removeSecurityProxy(dsd).base_version = versions["base"]

                # Add a couple of comments.
                self.factory.makeDistroSeriesDifferenceComment(dsd)
                self.factory.makeDistroSeriesDifferenceComment(dsd)

                # Update the spr, some with recipes, some with signing keys.
                # SPR.uploader references both, and the uploader is referenced
                # in the page.
                spr = dsd.source_pub.sourcepackagerelease
                if index % 2 == 0:
                    removeSecurityProxy(spr).source_package_recipe_build = (
                        self.factory.makeSourcePackageRecipeBuild(
                            sourcename=spr.sourcepackagename.name,
                            distroseries=derived_series))
                else:
                    removeSecurityProxy(spr).dscsigningkey = (
                        self.factory.makeGPGKey(owner=spr.creator))

        def flush_and_render():
            flush_database_caches()
            # Pull in the calling user's location so that it isn't recorded in
            # the query count; it causes the total to be fragile for no
            # readily apparent reason.
            self.simple_user.location
            with StormStatementRecorder() as recorder:
                view = create_initialized_view(
                    derived_series, '+localpackagediffs',
                    principal=self.simple_user)
                view()
            return recorder, view.cached_differences.batch.trueSize

        def statement_differ(rec1, rec2):
            wrapper = TextWrapper(break_long_words=False)

            def prepare_statements(rec):
                for statement in rec.statements:
                    for line in wrapper.wrap(statement):
                        yield line
                    yield "-" * wrapper.width

            def statement_diff():
                diff = difflib.ndiff(
                    list(prepare_statements(rec1)),
                    list(prepare_statements(rec2)))
                for line in diff:
                    yield "%s\n" % line

            return statement_diff

        # Render without differences and check the query count isn't silly.
        recorder1, batch_size = flush_and_render()
        self.assertThat(recorder1, HasQueryCount(LessThan(30)))
        self.addDetail(
            "statement-count-0-differences",
            text_content(u"%d" % recorder1.count))
        # Add some differences and render.
        add_differences(2)
        recorder2, batch_size = flush_and_render()
        self.addDetail(
            "statement-count-2-differences",
            text_content(u"%d" % recorder2.count))
        # Add more differences and render again.
        add_differences(2)
        recorder3, batch_size = flush_and_render()
        self.addDetail(
            "statement-count-4-differences",
            text_content(u"%d" % recorder3.count))
        # The last render should not need more queries than the previous.
        self.addDetail(
            "statement-diff", Content(
                UTF8_TEXT, statement_differ(recorder2, recorder3)))
        # Details about the number of statements per row.
        statement_count_per_row = (
            (recorder3.count - recorder1.count) / float(batch_size))
        self.addDetail(
            "statement-count-per-row-average",
            text_content(u"%.2f" % statement_count_per_row))
        # Query count is ~O(1) (i.e. not dependent of the number of
        # differences displayed).
        self.assertThat(
            recorder3, HasQueryCount(Equals(recorder2.count)))

    def test_queries_single_parent(self):
        dsp = self.factory.makeDistroSeriesParent()
        derived_series = dsp.derived_series
        self._assertQueryCount(derived_series)

    def test_queries_multiple_parents(self):
        dsp = self.factory.makeDistroSeriesParent()
        derived_series = dsp.derived_series
        self.factory.makeDistroSeriesParent(
            derived_series=derived_series)
        self._assertQueryCount(derived_series)


class TestDistroSeriesLocalDifferences(TestCaseWithFactory,
                                       DistroSeriesDifferenceMixin):
    """Test the distroseries +localpackagediffs view."""

    layer = LaunchpadFunctionalLayer

    def makePackageUpgrade(self, derived_series=None):
        """Create a `DistroSeriesDifference` for a package upgrade."""
        base_version = '1.%d' % self.factory.getUniqueInteger()
        versions = {
            'base': base_version,
            'parent': base_version + '-' + self.factory.getUniqueString(),
            'derived': base_version,
        }
        return self.factory.makeDistroSeriesDifference(
            derived_series=derived_series, versions=versions,
            set_base_version=True)

    def makeView(self, distroseries=None):
        """Create a +localpackagediffs view for `distroseries`."""
        if distroseries is None:
            distroseries = (
                self.factory.makeDistroSeriesParent().derived_series)
        # current_request=True causes the current interaction to end so we
        # must explicitly ask that the current principal be used for the
        # request.
        return create_initialized_view(
            distroseries, '+localpackagediffs',
            principal=get_current_principal(),
            current_request=True)

    def test_filter_form_if_differences(self):
        # Test that the page includes the filter form if differences
        # are present
        simple_user = self.factory.makePerson()
        login_person(simple_user)
        derived_series, parent_series = self._createChildAndParent()
        self.factory.makeDistroSeriesDifference(
            derived_series=derived_series)

        view = create_initialized_view(
            derived_series, '+localpackagediffs', principal=simple_user)

        self.assertIsNot(
            None,
            find_tag_by_id(view(), 'distroseries-localdiff-search-filter'),
            "Form filter should be shown when there are differences.")

    def test_parent_packagesets_localpackagediffs(self):
        # +localpackagediffs displays the packagesets.
        ds_diff = self.factory.makeDistroSeriesDifference()
        with celebrity_logged_in('admin'):
            ps = self.factory.makePackageset(
                packages=[ds_diff.source_package_name],
                distroseries=ds_diff.derived_series)

        simple_user = self.factory.makePerson()
        with person_logged_in(simple_user):
            view = create_initialized_view(
                ds_diff.derived_series,
                '+localpackagediffs',
                principal=simple_user)
            html_content = view()

        packageset_text = re.compile('\s*' + ps.name)
        self._test_packagesets(
            html_content, packageset_text, 'packagesets',
            'Packagesets')

    def test_parent_packagesets_localpackagediffs_sorts(self):
        # Multiple packagesets are sorted in a comma separated list.
        ds_diff = self.factory.makeDistroSeriesDifference()
        unsorted_names = [u"zzz", u"aaa"]
        with celebrity_logged_in('admin'):
            for name in unsorted_names:
                self.factory.makePackageset(
                    name=name,
                    packages=[ds_diff.source_package_name],
                    distroseries=ds_diff.derived_series)

        simple_user = self.factory.makePerson()
        with person_logged_in(simple_user):
            view = create_initialized_view(
                ds_diff.derived_series,
                '+localpackagediffs',
                principal=simple_user)
            html_content = view()

        packageset_text = re.compile(
            '\s*' + ', '.join(sorted(unsorted_names)))
        self._test_packagesets(
            html_content, packageset_text, 'packagesets',
            'Packagesets')

    def test_label(self):
        # The view label includes the names of both series.
        derived_series, parent_series = self._createChildAndParent()

        view = self.makeView(derived_series)

        self.assertEqual(
            "Source package differences between 'Derilucid' and "
            "parent series 'Lucid'",
            view.label)

    def test_label_multiple_parents(self):
        # If the series has multiple parents, the view label mentions
        # the generic term 'parent series'.
        derived_series, parent_series = self._createChildAndParents()

        view = create_initialized_view(
            derived_series, '+localpackagediffs')

        self.assertEqual(
            "Source package differences between 'Derilucid' and "
            "parent series",
            view.label)

    def test_batch_includes_needing_attention_only(self):
        # The differences attribute includes differences needing
        # attention only.
        derived_series, parent_series = self._createChildAndParent()
        current_difference = self.factory.makeDistroSeriesDifference(
            derived_series=derived_series)
        self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            status=DistroSeriesDifferenceStatus.RESOLVED)

        view = self.makeView(derived_series)

        self.assertContentEqual(
            [current_difference], view.cached_differences.batch)

    def test_batch_includes_different_versions_only(self):
        # The view contains differences of type DIFFERENT_VERSIONS only.
        derived_series, parent_series = self._createChildAndParent()
        different_versions_diff = self.factory.makeDistroSeriesDifference(
            derived_series=derived_series)
        self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            difference_type=(
                DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES))

        view = self.makeView(derived_series)

        self.assertContentEqual(
            [different_versions_diff], view.cached_differences.batch)

    def test_template_includes_help_link(self):
        # The help link for popup help is included.
        derived_series, parent_series = self._createChildAndParent()
        view = self.makeView(derived_series)

        soup = BeautifulSoup(view())
        help_links = soup.findAll(
            'a', href='/+help-soyuz/derived-series-syncing.html')
        self.assertEqual(1, len(help_links))

    def test_diff_row_includes_last_comment_only(self):
        # The most recent comment is rendered for each difference.
        derived_series, parent_series = self._createChildAndParent()
        difference = self.factory.makeDistroSeriesDifference(
            derived_series=derived_series)
        with person_logged_in(derived_series.owner):
            difference.addComment(difference.owner, "Earlier comment")
            difference.addComment(difference.owner, "Latest comment")

        view = self.makeView(derived_series)

        # Find all the rows within the body of the table
        # listing the differences.
        soup = BeautifulSoup(view())
        diff_table = soup.find('table', {'class': 'listing'})
        rows = diff_table.tbody.findAll('tr')

        self.assertEqual(1, len(rows))
        self.assertIn("Latest comment", unicode(rows[0]))
        self.assertNotIn("Earlier comment", unicode(rows[0]))

    def test_diff_row_links_to_extra_details(self):
        # The source package name links to the difference details.
        derived_series, parent_series = self._createChildAndParent()
        difference = self.factory.makeDistroSeriesDifference(
            derived_series=derived_series)

        view = self.makeView(derived_series)
        soup = BeautifulSoup(view())
        diff_table = soup.find('table', {'class': 'listing'})
        row = diff_table.tbody.findAll('tr')[0]

        links = row.findAll('a', href=canonical_url(difference))
        self.assertEqual(1, len(links))
        self.assertEqual(difference.source_package_name.name, links[0].string)

    def test_multiple_parents_display(self):
        package_name = 'package-1'
        other_parent_series = self.factory.makeDistroSeries(name='other')
        derived_series, parent_series = self._createChildAndParents(
            other_parent_series=other_parent_series)
        versions = {
            'base': u'1.0',
            'derived': u'1.0derived1',
            'parent': u'1.0-1',
        }

        self.factory.makeDistroSeriesDifference(
            versions=versions,
            parent_series=other_parent_series,
            source_package_name_str=package_name,
            derived_series=derived_series)
        self.factory.makeDistroSeriesDifference(
            versions=versions,
            parent_series=parent_series,
            source_package_name_str=package_name,
            derived_series=derived_series)
        view = create_initialized_view(
            derived_series, '+localpackagediffs')
        multiple_parents_matches = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                "Parent table header", 'th',
                text=re.compile("\s*Parent\s")),
            soupmatchers.Tag(
                "Parent version table header", 'th',
                text=re.compile("\s*Parent version\s*")),
            soupmatchers.Tag(
                "Parent name", 'a',
                attrs={'class': 'parent-name'},
                text=re.compile("\s*Other\s*")),
             )
        self.assertThat(view.render(), multiple_parents_matches)

    def test_diff_row_shows_version_attached(self):
        # The +localpackagediffs page shows the version attached to the
        # DSD and not the last published version (bug=745776).
        package_name = 'package-1'
        derived_series, parent_series = self._createChildAndParent()
        versions = {
            'base': u'1.0',
            'derived': u'1.0derived1',
            'parent': u'1.0-1',
        }
        new_version = u'1.2'

        difference = self.factory.makeDistroSeriesDifference(
            versions=versions,
            source_package_name_str=package_name,
            derived_series=derived_series)

        # Create a more recent source package publishing history.
        sourcepackagename = self.factory.getOrMakeSourcePackageName(
            package_name)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=sourcepackagename,
            distroseries=derived_series,
            version=new_version)

        view = self.makeView(derived_series)
        soup = BeautifulSoup(view())
        diff_table = soup.find('table', {'class': 'listing'})
        row = diff_table.tbody.tr
        links = row.findAll('a', {'class': 'derived-version'})

        # The version displayed is the version attached to the
        # difference.
        self.assertEqual(1, len(links))
        self.assertEqual(versions['derived'], links[0].string.strip())

        link = canonical_url(difference.source_pub.sourcepackagerelease)
        self.assertTrue(link, EndsWith(new_version))
        # The link points to the sourcepackagerelease referenced in the
        # difference.
        self.assertTrue(
            links[0].get('href'), EndsWith(difference.source_version))

    def test_diff_row_no_published_version(self):
        # The +localpackagediffs page shows only the version (no link)
        # if we fail to fetch the published version.
        package_name = 'package-1'
        derived_series, parent_series = self._createChildAndParent()
        versions = {
            'base': u'1.0',
            'derived': u'1.0derived1',
            'parent': u'1.0-1',
        }

        difference = self.factory.makeDistroSeriesDifference(
            versions=versions,
            source_package_name_str=package_name,
            derived_series=derived_series)

        # Delete the publications.
        removeSecurityProxy(difference.source_pub).status = (
            PackagePublishingStatus.DELETED)
        removeSecurityProxy(difference.parent_source_pub).status = (
            PackagePublishingStatus.DELETED)
        # Flush out the changes and invalidate caches (esp. property caches).
        flush_database_caches()

        view = self.makeView(derived_series)
        soup = BeautifulSoup(view())
        diff_table = soup.find('table', {'class': 'listing'})
        row = diff_table.tbody.tr

        # The table feature a simple span since we were unable to fetch a
        # published sourcepackage.
        derived_span = row.findAll('span', {'class': 'derived-version'})
        parent_span = row.findAll('span', {'class': 'parent-version'})
        self.assertEqual(1, len(derived_span))
        self.assertEqual(1, len(parent_span))

        # The versions displayed are the versions attached to the
        # difference.
        self.assertEqual(versions['derived'], derived_span[0].string.strip())
        self.assertEqual(versions['parent'], parent_span[0].string.strip())

    def test_diff_row_last_changed(self):
        # The SPR creator (i.e. who make the package change, rather than the
        # uploader) is shown on each difference row.
        dsd = self.makePackageUpgrade()
        view = self.makeView(dsd.derived_series)
        root = html.fromstring(view())
        [creator_cell] = root.cssselect(
            "table.listing tbody td.last-changed")
        self.assertIn(
            "by %s" % (
                dsd.source_package_release.creator.displayname,),
            normalize_whitespace(creator_cell.text_content()))

    def test_diff_row_last_changed_also_shows_uploader_if_different(self):
        # When the SPR creator and uploader are different both are named on
        # each difference row.
        dsd = self.makePackageUpgrade()
        uploader = self.factory.makePerson()
        removeSecurityProxy(dsd.source_package_release).dscsigningkey = (
            self.factory.makeGPGKey(uploader))
        view = self.makeView(dsd.derived_series)
        root = html.fromstring(view())
        [creator_cell] = root.cssselect(
            "table.listing tbody td.last-changed")
        matches = DocTestMatches(
            "... ago by %s (uploaded by %s)" % (
                dsd.source_package_release.creator.displayname,
                dsd.source_package_release.dscsigningkey.owner.displayname))
        self.assertThat(creator_cell.text_content(), matches)

    def test_diff_row_links_to_parent_changelog(self):
        # After the parent's version, there should be text "(changelog)"
        # linked to the parent distro source package +changelog page.  The
        # text is styled with "lesser".
        dsd = self.makePackageUpgrade()
        view = self.makeView(dsd.derived_series)
        soup = BeautifulSoup(view())
        diff_table = soup.find('table', {'class': 'listing'})
        row = diff_table.tbody.tr

        changelog_span = row.findAll('span', {'class': 'lesser'})
        self.assertEqual(1, len(changelog_span))
        link = changelog_span[0].a
        self.assertEqual("changelog", link.string)

        parent_dsp = dsd.parent_series.distribution.getSourcePackage(
            dsd.source_package_name)
        expected_url = urlappend(canonical_url(parent_dsp), '+changelog')
        self.assertEqual(expected_url, link.attrs[0][1])

    def test_getUpgrades_shows_updates_in_parent(self):
        # The view's getUpgrades methods lists packages that can be
        # trivially upgraded: changed in the parent, not changed in the
        # derived series, but present in both.
        dsd = self.makePackageUpgrade()
        view = self.makeView(dsd.derived_series)
        self.assertContentEqual([dsd], view.getUpgrades())

    def enableDerivedSeriesUpgradeFeature(self):
        """Enable the feature flag for derived-series upgrade."""
        self.useFixture(
            FeatureFixture(
                {u'soyuz.derived_series_upgrade.enabled': u'on'}))

    @with_celebrity_logged_in("admin")
    def test_upgrades_offered_only_with_feature_flag(self):
        # The "Upgrade Packages" button will only be shown when a specific
        # feature flag is enabled.
        view = self.makeView()
        self.makePackageUpgrade(view.context)
        self.assertFalse(view.canUpgrade())
        self.enableDerivedSeriesUpgradeFeature()
        self.assertTrue(view.canUpgrade())

    def test_upgrades_are_offered_if_appropriate(self):
        # The "Upgrade Packages" button will only be shown to privileged
        # users.
        self.enableDerivedSeriesUpgradeFeature()
        dsd = self.makePackageUpgrade()
        view = self.makeView(dsd.derived_series)
        with celebrity_logged_in("admin"):
            self.assertTrue(view.canUpgrade())
        with person_logged_in(self.factory.makePerson()):
            self.assertFalse(view.canUpgrade())
        with anonymous_logged_in():
            self.assertFalse(view.canUpgrade())

    @with_celebrity_logged_in("admin")
    def test_upgrades_offered_only_if_available(self):
        # If there are no upgrades, the "Upgrade Packages" button won't
        # be shown.
        self.enableDerivedSeriesUpgradeFeature()
        view = self.makeView()
        self.assertFalse(view.canUpgrade())
        self.makePackageUpgrade(view.context)
        self.assertTrue(view.canUpgrade())

    @with_celebrity_logged_in("admin")
    def test_upgrades_not_offered_after_feature_freeze(self):
        # There won't be an "Upgrade Packages" button once feature
        # freeze has occurred.  Mass updates would not make sense after
        # that point.
        self.enableDerivedSeriesUpgradeFeature()
        upgradeable = {}
        for status in SeriesStatus.items:
            dsd = self.makePackageUpgrade()
            dsd.derived_series.status = status
            view = self.makeView(dsd.derived_series)
            upgradeable[status] = view.canUpgrade()
        expected = {
            SeriesStatus.FUTURE: True,
            SeriesStatus.EXPERIMENTAL: True,
            SeriesStatus.DEVELOPMENT: True,
            SeriesStatus.FROZEN: False,
            SeriesStatus.CURRENT: False,
            SeriesStatus.SUPPORTED: False,
            SeriesStatus.OBSOLETE: False,
        }
        self.assertEqual(expected, upgradeable)

    def test_upgrade_creates_sync_jobs(self):
        # requestUpgrades generates PackageCopyJobs for the upgrades
        # that need doing.
        dsd = self.makePackageUpgrade()
        series = dsd.derived_series
        with celebrity_logged_in('admin'):
            series.status = SeriesStatus.DEVELOPMENT
            series.datereleased = UTC_NOW
        view = self.makeView(series)
        view.requestUpgrades()
        job_source = getUtility(IPlainPackageCopyJobSource)
        jobs = list(
            job_source.getActiveJobs(series.distribution.main_archive))
        self.assertEquals(1, len(jobs))
        job = jobs[0]
        self.assertEquals(series, job.target_distroseries)
        self.assertEqual(dsd.source_package_name.name, job.package_name)
        self.assertEqual(dsd.parent_source_version, job.package_version)
        self.assertEqual(PackagePublishingPocket.RELEASE, job.target_pocket)

    def test_upgrade_gives_feedback(self):
        # requestUpgrades doesn't instantly perform package upgrades,
        # but it shows the user a notice that the upgrades have been
        # requested.
        dsd = self.makePackageUpgrade()
        view = self.makeView(dsd.derived_series)
        view.requestUpgrades()
        expected = {
            "level": BrowserNotificationLevel.INFO,
            "message":
                ("Upgrades of {0.displayname} packages have been "
                 "requested. Please give Launchpad some time to "
                 "complete these.").format(dsd.derived_series),
            }
        observed = map(vars, view.request.response.notifications)
        self.assertEqual([expected], observed)

    def test_requestUpgrades_is_efficient(self):
        # A single web request may need to schedule large numbers of
        # package upgrades.  It must do so without issuing large numbers
        # of database queries.
        derived_series, parent_series = self._createChildAndParent()
        # Take a baseline measure of queries.
        self.makePackageUpgrade(derived_series=derived_series)
        flush_database_caches()
        with StormStatementRecorder() as recorder1:
            self.makeView(derived_series).requestUpgrades()
        self.assertThat(recorder1, HasQueryCount(LessThan(12)))

        # The query count does not increase with the number of upgrades.
        for index in xrange(3):
            self.makePackageUpgrade(derived_series=derived_series)
        flush_database_caches()
        with StormStatementRecorder() as recorder2:
            self.makeView(derived_series).requestUpgrades()
        self.assertThat(
            recorder2,
            HasQueryCount(Equals(recorder1.count)))

    def makeDSDJob(self, dsd):
        """Create a `DistroSeriesDifferenceJob` to update `dsd`."""
        job_source = getUtility(IDistroSeriesDifferenceJobSource)
        jobs = job_source.createForPackagePublication(
            dsd.derived_series, dsd.source_package_name,
            PackagePublishingPocket.RELEASE)
        return jobs[0]

    def test_higher_radio_mentions_parent(self):
        # The user is shown an option to display only the blacklisted
        # package with a higher version than in the parent.
        derived_series, parent_series = self._createChildAndParent()
        self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            source_package_name_str="my-src-package")
        view = create_initialized_view(
            derived_series,
            '+localpackagediffs')

        radio_title = (
            "&nbsp;Ignored packages with a higher version than in "
            "&#x27;Lucid&#x27;")
        radio_option_matches = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                "radio displays parent's name", 'label',
                text=radio_title),
            )
        self.assertThat(view.render(), radio_option_matches)

    def test_higher_radio_mentions_parents(self):
        derived_series, parent_series = self._createChildAndParents()
        self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            source_package_name_str="my-src-package")
        view = create_initialized_view(
            derived_series,
            '+localpackagediffs')

        radio_title = \
            "&nbsp;Ignored packages with a higher version than in parent"
        radio_option_matches = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                "radio displays parent's name", 'label',
                text=radio_title),
            )
        self.assertThat(view.render(), radio_option_matches)

    def _set_source_selection(self, series):
        # Set up source package format selection so that copying will
        # work with the default dsc_format used in
        # makeSourcePackageRelease.
        getUtility(ISourcePackageFormatSelectionSet).add(
            series, SourcePackageFormat.FORMAT_1_0)

    def test_batch_filtered(self):
        # The name_filter parameter allows filtering of packages by name.
        derived_series, parent_series = self._createChildAndParent()
        diff1 = self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            source_package_name_str="my-src-package")
        diff2 = self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            source_package_name_str="my-second-src-package")

        filtered_view = create_initialized_view(
            derived_series,
            '+localpackagediffs',
            query_string='field.name_filter=my-src-package')
        unfiltered_view = create_initialized_view(
            derived_series,
            '+localpackagediffs')

        self.assertContentEqual(
            [diff1], filtered_view.cached_differences.batch)
        self.assertContentEqual(
            [diff2, diff1], unfiltered_view.cached_differences.batch)

    def test_batch_non_blacklisted(self):
        # The default filter is all non blacklisted differences.
        derived_series, parent_series = self._createChildAndParent()
        diff1 = self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            source_package_name_str="my-src-package")
        diff2 = self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            source_package_name_str="my-second-src-package")
        self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            status=DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT)

        filtered_view = create_initialized_view(
            derived_series,
            '+localpackagediffs',
            query_string='field.package_type=%s' % NON_IGNORED)
        filtered_view2 = create_initialized_view(
            derived_series,
            '+localpackagediffs')

        self.assertContentEqual(
            [diff2, diff1], filtered_view.cached_differences.batch)
        self.assertContentEqual(
            [diff2, diff1], filtered_view2.cached_differences.batch)

    def test_batch_all_packages(self):
        # field.package_type parameter allows to list all the
        # differences.
        derived_series, parent_series = self._createChildAndParent()
        # Create differences of all possible statuses.
        diffs = []
        for status in DistroSeriesDifferenceStatus.items:
            diff = self.factory.makeDistroSeriesDifference(
                derived_series=derived_series, status=status)
            diffs.append(diff)
        all_view = create_initialized_view(
            derived_series,
            '+localpackagediffs',
            query_string='field.package_type=%s' % ALL)

        self.assertContentEqual(diffs, all_view.cached_differences.batch)

    def test_batch_wrong_param(self):
        # If a wrong parameter is passed then an error is displayed
        # and no differences are shown.
        derived_series, parent_series = self._createChildAndParent()
        self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            source_package_name_str="my-src-package")
        view = create_initialized_view(
            derived_series,
            '+localpackagediffs',
            query_string='field.package_type=%s' % 'unexpected')
        view()  # Render the view.

        self.assertEqual('Invalid option', view.getFieldError('package_type'))
        self.assertContentEqual([], view.cached_differences.batch)

    def test_batch_blacklisted_differences_with_higher_version(self):
        # field.package_type parameter allows to list only
        # blacklisted differences with a child's version higher than parent's.
        derived_series, parent_series = self._createChildAndParent()
        blacklisted_diff_higher = self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            status=DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT,
            versions={'base': '1.1', 'parent': '1.3', 'derived': '1.10'})
        self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            status=DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT,
            versions={'base': '1.1', 'parent': '1.12', 'derived': '1.10'})

        blacklisted_view = create_initialized_view(
            derived_series,
            '+localpackagediffs',
            query_string='field.package_type=%s' % HIGHER_VERSION_THAN_PARENT)
        unblacklisted_view = create_initialized_view(
            derived_series,
            '+localpackagediffs')

        self.assertContentEqual(
            [blacklisted_diff_higher],
            blacklisted_view.cached_differences.batch)
        self.assertContentEqual(
            [], unblacklisted_view.cached_differences.batch)

    def test_batch_resolved_differences(self):
        # Test that we can search for differences that we marked
        # resolved.
        derived_series, parent_series = self._createChildAndParent()

        self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            source_package_name_str="my-src-package")
        self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            source_package_name_str="my-second-src-package")
        resolved_diff = self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            status=DistroSeriesDifferenceStatus.RESOLVED)

        filtered_view = create_initialized_view(
            derived_series,
            '+localpackagediffs',
            query_string='field.package_type=%s' % RESOLVED)

        self.assertContentEqual(
            [resolved_diff], filtered_view.cached_differences.batch)

    def _setUpDSD(self, src_name='src-name', versions=None,
                  difference_type=None, distribution=None):
        # Helper to create a derived series with fixed names and proper
        # source package format selection along with a DSD.
        parent_series = self.factory.makeDistroSeries()
        if distribution == None:
            distribution = self.factory.makeDistribution()
        derived_series = self.factory.makeDistroSeries(
            distribution=distribution)
        self.factory.makeDistroSeriesParent(
            derived_series=derived_series, parent_series=parent_series)
        self._set_source_selection(derived_series)
        diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str=src_name,
            derived_series=derived_series, versions=versions,
            difference_type=difference_type)
        sourcepackagename = self.factory.getOrMakeSourcePackageName(
            src_name)
        return derived_series, parent_series, sourcepackagename, str(diff.id)

    def test_canPerformSync_anon(self):
        # Anonymous users cannot sync packages.
        derived_series = self._setUpDSD()[0]
        view = create_initialized_view(
            derived_series, '+localpackagediffs')

        self.assertFalse(view.canPerformSync())

    def test_canPerformSync_non_anon_no_perm_dest_archive(self):
        # Logged-in users with no permission on the destination archive
        # are not presented with options to perform syncs.
        derived_series = self._setUpDSD()[0]
        with person_logged_in(self.factory.makePerson()):
            view = create_initialized_view(
                derived_series, '+localpackagediffs')

            self.assertFalse(view.canPerformSync())

    def _setUpPersonWithPerm(self, derived_series):
        # Helper to create a person with an upload permission on the
        # series' archive.
        person = self.factory.makePerson()
        ArchivePermission(
            archive=derived_series.main_archive, person=person,
            component=getUtility(IComponentSet)["main"],
            permission=ArchivePermissionType.QUEUE_ADMIN)
        return person

    def test_canPerformSync_non_anon(self):
        # Logged-in users with a permission on the destination archive
        # are presented with options to perform syncs.
        # Note that a more fine-grained perm check is done on each
        # synced package.
        derived_series = self._setUpDSD()[0]
        person = self._setUpPersonWithPerm(derived_series)
        with person_logged_in(person):
            view = create_initialized_view(
                derived_series, '+localpackagediffs')

            self.assertTrue(view.canPerformSync())

    def test_hasPendingDSDUpdate_returns_False_if_no_pending_update(self):
        dsd = self.factory.makeDistroSeriesDifference()
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        self.assertFalse(view.hasPendingDSDUpdate(dsd))

    def test_hasPendingDSDUpdate_returns_True_if_pending_update(self):
        dsd = self.factory.makeDistroSeriesDifference()
        self.makeDSDJob(dsd)
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        self.assertTrue(view.hasPendingDSDUpdate(dsd))

    def test_pendingSync_returns_None_if_no_pending_sync(self):
        dsd = self.factory.makeDistroSeriesDifference()
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        self.assertIs(None, view.pendingSync(dsd))

    def test_pendingSync_returns_not_None_if_pending_sync(self):
        dsd = self.factory.makeDistroSeriesDifference()
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        get_property_cache(view).pending_syncs = {
            dsd.source_package_name.name: object(),
            }
        self.assertIsNot(None, view.pendingSync(dsd))

    def test_isNewerThanParent_compares_versions_not_strings(self):
        # isNewerThanParent compares Debian-style version numbers, not
        # raw version strings.  So it's possible for a child version to
        # be considered newer than the corresponding parent version even
        # though a string comparison goes the other way.
        versions = dict(base='1.0', parent='1.1c', derived='1.10')
        dsd = self.factory.makeDistroSeriesDifference(versions=versions)
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')

        # Assumption for the test: the child version is greater than the
        # parent version, but a string comparison puts them the other
        # way around.
        self.assertFalse(versions['parent'] < versions['derived'])
        self.assertTrue(
            Version(versions['parent']) < Version(versions['derived']))

        # isNewerThanParent is not fooled by the misleading string
        # comparison.
        self.assertTrue(view.isNewerThanParent(dsd))

    def test_isNewerThanParent_is_False_for_parent_update(self):
        dsd = self.factory.makeDistroSeriesDifference(
            versions=dict(base='1.0', parent='1.1', derived='1.0'))
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        self.assertFalse(view.isNewerThanParent(dsd))

    def test_isNewerThanParent_is_False_for_equivalent_updates(self):
        # Some non-identical version numbers compare as "equal".  If the
        # child and parent versions compare as equal, the child version
        # is not considered newer.
        dsd = self.factory.makeDistroSeriesDifference(
            versions=dict(base='1.0', parent='1.1', derived='1.1'))
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        self.assertFalse(view.isNewerThanParent(dsd))

    def test_isNewerThanParent_is_True_for_child_update(self):
        dsd = self.factory.makeDistroSeriesDifference(
            versions=dict(base='1.0', parent='1.0', derived='1.1'))
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        self.assertTrue(view.isNewerThanParent(dsd))

    def test_canRequestSync_returns_False_if_pending_sync(self):
        dsd = self.factory.makeDistroSeriesDifference()
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        get_property_cache(view).pending_syncs = {
            dsd.source_package_name.name: object(),
            }
        self.assertFalse(view.canRequestSync(dsd))

    def test_canRequestSync_returns_False_if_child_is_newer(self):
        dsd = self.factory.makeDistroSeriesDifference(
            versions=dict(base='1.0', parent='1.0', derived='1.1'))
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        self.assertFalse(view.canRequestSync(dsd))

    def test_canRequestSync_returns_True_if_sync_makes_sense(self):
        dsd = self.factory.makeDistroSeriesDifference()
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        self.assertTrue(view.canRequestSync(dsd))

    def test_canRequestSync_ignores_DSDJobs(self):
        dsd = self.factory.makeDistroSeriesDifference()
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        view.hasPendingDSDUpdate = FakeMethod(result=True)
        self.assertTrue(view.canRequestSync(dsd))

    def test_canRequestSync_returns_False_if_DSD_is_resolved(self):
        dsd = self.factory.makeDistroSeriesDifference(
            versions=dict(base='1.0', parent='1.1', derived='1.1'),
            status=DistroSeriesDifferenceStatus.RESOLVED)
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        self.assertFalse(view.canRequestSync(dsd))

    def test_describeJobs_returns_None_if_no_jobs(self):
        dsd = self.factory.makeDistroSeriesDifference()
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        self.assertIs(None, view.describeJobs(dsd))

    def test_describeJobs_reports_pending_update(self):
        dsd = self.factory.makeDistroSeriesDifference()
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        view.hasPendingDSDUpdate = FakeMethod(result=True)
        view.pendingSync = FakeMethod(result=None)
        self.assertEqual("updating&hellip;", view.describeJobs(dsd))

    def test_describeJobs_reports_pending_sync(self):
        dsd = self.factory.makeDistroSeriesDifference()
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        view.hasPendingDSDUpdate = FakeMethod(result=False)
        pcj = self.factory.makePlainPackageCopyJob()
        get_property_cache(view).pending_syncs = {
            dsd.source_package_name.name: pcj,
            }
        self.assertEqual("synchronizing&hellip;", view.describeJobs(dsd))

    def test_describeJobs_reports_pending_queue(self):
        dsd = self.factory.makeDistroSeriesDifference()
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        view.hasPendingDSDUpdate = FakeMethod(result=False)
        pcj = self.factory.makePlainPackageCopyJob()
        pu = self.factory.makePackageUpload(distroseries=dsd.derived_series)
        # A copy job with an attached packageupload means the job is
        # waiting in the queues.
        removeSecurityProxy(pu).package_copy_job = pcj.id
        get_property_cache(view).pending_syncs = {
            dsd.source_package_name.name: pcj,
            }
        expected = (
            'waiting in <a href="%s/+queue?queue_state=%s">%s</a>&hellip;'
            % (canonical_url(dsd.derived_series), pu.status.value,
               pu.status.name))
        self.assertEqual(expected, view.describeJobs(dsd))

    def test_describeJobs_reports_pending_sync_and_update(self):
        dsd = self.factory.makeDistroSeriesDifference()
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        view.hasPendingDSDUpdate = FakeMethod(result=True)
        pcj = self.factory.makePlainPackageCopyJob()
        self.factory.makePackageUpload(distroseries=dsd.derived_series,
                                       package_copy_job=pcj.id)
        get_property_cache(view).pending_syncs = {
            dsd.source_package_name.name: pcj,
            }
        self.assertEqual(
            "updating and synchronizing&hellip;", view.describeJobs(dsd))

    def _syncAndGetView(self, derived_series, person, sync_differences,
                        difference_type=None, view_name='+localpackagediffs',
                        query_string='', sponsored=None):
        # A helper to get the POST'ed sync view.
        with person_logged_in(person):
            form = {
                'field.selected_differences': sync_differences,
                'field.actions.sync': 'Sync',
                }
            if sponsored is not None:
                form['field.sponsored_person'] = sponsored.name
            view = create_initialized_view(
                derived_series, view_name,
                method='POST', form=form,
                query_string=query_string)
            return view

    def test_sync_error_nothing_selected(self):
        # An error is raised when a sync is requested without any selection.
        derived_series = self._setUpDSD()[0]
        person = self._setUpPersonWithPerm(derived_series)
        view = self._syncAndGetView(derived_series, person, [])

        self.assertEqual(1, len(view.errors))
        self.assertEqual(
            'No differences selected.', view.errors[0])

    def test_sync_error_invalid_selection(self):
        # An error is raised when an invalid difference is selected.
        derived_series, unused, unused2, diff_id = self._setUpDSD(
            'my-src-name')
        person = self._setUpPersonWithPerm(derived_series)
        another_id = str(int(diff_id) + 1)
        view = self._syncAndGetView(
            derived_series, person, [another_id])

        self.assertEqual(2, len(view.errors))
        self.assertEqual(
            'No differences selected.', view.errors[0])
        self.assertEqual(
            'Invalid value', view.errors[1].error_name)

    def test_sync_error_no_perm_dest_archive(self):
        # A user without upload rights on the destination archive cannot
        # sync packages.
        derived_series, unused, unused2, diff_id = self._setUpDSD(
            'my-src-name')
        person = self._setUpPersonWithPerm(derived_series)
        view = self._syncAndGetView(
            derived_series, person, [diff_id])

        self.assertEqual(1, len(view.errors))
        self.assertTrue(
            html_escape(
                "The signer of this package has no upload rights to this "
                "distribution's primary archive") in view.errors[0])

    def makePersonWithComponentPermission(self, archive, component=None):
        person = self.factory.makePerson()
        if component is None:
            component = self.factory.makeComponent()
        removeSecurityProxy(archive).newComponentUploader(
            person, component)
        return person, component

    def test_sync_success_perm_component(self):
        # A user with upload rights on the destination component
        # can sync packages.
        derived_series, parent_series, sp_name, diff_id = self._setUpDSD(
            'my-src-name')
        person, _ = self.makePersonWithComponentPermission(
            derived_series.main_archive,
            derived_series.getSourcePackage(
                sp_name).latest_published_component)
        view = self._syncAndGetView(
            derived_series, person, [diff_id])

        self.assertEqual(0, len(view.errors))

    def test_sync_error_no_perm_component(self):
        # A user without upload rights on the destination component
        # will get an error when he syncs packages to this component.
        derived_series, parent_series, unused, diff_id = self._setUpDSD(
            'my-src-name')
        person, another_component = self.makePersonWithComponentPermission(
            derived_series.main_archive)
        view = self._syncAndGetView(
            derived_series, person, [diff_id])

        self.assertEqual(1, len(view.errors))
        self.assertTrue(
            "Signer is not permitted to upload to the "
            "component" in view.errors[0])

    def test_sync_with_sponsoring(self):
        # The requesting user can set a sponsored person on the sync. We
        # need to make sure the sponsored person ends up on the copy job
        # metadata.
        derived_series, parent_series, sp_name, diff_id = self._setUpDSD(
            'my-src-name')
        person, _ = self.makePersonWithComponentPermission(
            derived_series.main_archive,
            derived_series.getSourcePackage(
                sp_name).latest_published_component)
        sponsored_person = self.factory.makePerson()
        self._syncAndGetView(
            derived_series, person, [diff_id],
            sponsored=sponsored_person)

        pcj = PlainPackageCopyJob.getActiveJobs(
            derived_series.main_archive).one()
        self.assertEqual(pcj.sponsored, sponsored_person)

    def assertPackageCopied(self, series, src_name, version, view):
        # Helper to check that a package has been copied by virtue of
        # there being a package copy job ready to run.
        pcj = PlainPackageCopyJob.getActiveJobs(series.main_archive).one()
        self.assertEqual(version, pcj.package_version)

        # The view should show no errors, and the notification should
        # confirm the sync worked.
        self.assertEqual(0, len(view.errors))
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        self.assertIn("Requested sync of 1 package", notifications[0].message)
        # 302 is a redirect back to the same page.
        self.assertEqual(302, view.request.response.getStatus())

    def test_sync_success(self):
        # A user with upload rights on the destination archive can sync
        # packages. Notifications about the synced packages are displayed and
        # the packages are copied inside the destination series.
        versions = {
            'base': '1.0',
            'derived': '1.0derived1',
            'parent': '1.0-1',
        }
        derived_series, parent_series, sp_name, diff_id = self._setUpDSD(
            'my-src-name', versions=versions)

        # Setup a user with upload rights.
        person = self.factory.makePerson()
        removeSecurityProxy(derived_series.main_archive).newPackageUploader(
            person, sp_name)

        # The inital state is that 1.0-1 is not in the derived series.
        pubs = derived_series.main_archive.getPublishedSources(
            name=u'my-src-name', version=versions['parent'],
            distroseries=derived_series).any()
        self.assertIs(None, pubs)

        # Now, sync the source from the parent using the form.
        view = self._syncAndGetView(
            derived_series, person, [diff_id], query_string=(
                "batch=12&start=24&my-old-man=dustman"))

        # The parent's version should now be in the derived series and
        # the notifications displayed:
        self.assertPackageCopied(
            derived_series, 'my-src-name', versions['parent'], view)

        # The URL to which the browser is redirected has same batch and
        # filtering options as where the sync request was made.
        self.assertEqual(
            "batch=12&start=24&my-old-man=dustman",
            urlparse(view.next_url).query)

    def test_sync_success_not_yet_in_derived_series(self):
        # If the package to sync does not exist yet in the derived series,
        # upload right to any component inside the destination series will be
        # enough to sync the package.
        versions = {
            'parent': '1.0-1',
        }
        missing = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        derived_series, parent_series, unused, diff_id = self._setUpDSD(
            'my-src-name', difference_type=missing, versions=versions)
        person, another_component = self.makePersonWithComponentPermission(
            derived_series.main_archive)
        view = self._syncAndGetView(
            derived_series, person, [diff_id],
            view_name='+missingpackages')

        self.assertPackageCopied(
            derived_series, 'my-src-name', versions['parent'], view)

    def test_sync_in_released_series_in_updates(self):
        # If the destination series is released, the sync packages end
        # up in the updates pocket.
        versions = {
            'parent': '1.0-1',
            }
        derived_series, parent_series, sp_name, diff_id = self._setUpDSD(
            'my-src-name', versions=versions)
        # Update destination series status to current and update
        # daterelease.
        with celebrity_logged_in('admin'):
            derived_series.status = SeriesStatus.CURRENT
            derived_series.datereleased = UTC_NOW

        person = self.factory.makePerson()
        removeSecurityProxy(derived_series.main_archive).newPackageUploader(
            person, sp_name)
        self._syncAndGetView(
            derived_series, person, [diff_id])
        parent_series.main_archive.getPublishedSources(
            name=u'my-src-name', version=versions['parent'],
            distroseries=parent_series).one()

        # We look for a PackageCopyJob with the right metadata.
        pcj = PlainPackageCopyJob.getActiveJobs(
            derived_series.main_archive).one()
        self.assertEqual(PackagePublishingPocket.UPDATES, pcj.target_pocket)

    def test_diff_view_action_url(self):
        # The difference pages have a fixed action_url so that the sync
        # form self-posts.
        derived_series, parent_series, unused, diff_id = self._setUpDSD(
            'my-src-name')
        person = self.factory.makePerson()
        with person_logged_in(person):
            view = create_initialized_view(
                derived_series, '+localpackagediffs', method='GET',
                query_string='start=1&batch=1')

        self.assertEquals(
            'http://127.0.0.1?start=1&batch=1',
            view.action_url)

    def test_specified_packagesets_filter_none_specified(self):
        # specified_packagesets_filter is None when there are no
        # field.packageset parameters in the query.
        dsd = self.factory.makeDistroSeriesDifference()
        person = dsd.derived_series.owner
        with person_logged_in(person):
            view = create_initialized_view(
                dsd.derived_series, '+localpackagediffs', method='GET',
                query_string='')
            self.assertIs(None, view.specified_packagesets_filter)

    def test_specified_packagesets_filter_specified(self):
        # specified_packagesets_filter returns a collection of Packagesets
        # when there are field.packageset query parameters.
        dsd = self.factory.makeDistroSeriesDifference()
        person = dsd.derived_series.owner
        packageset1 = self.factory.makePackageset(
            distroseries=dsd.derived_series)
        packageset2 = self.factory.makePackageset(
            distroseries=dsd.derived_series)
        with person_logged_in(person):
            view = create_initialized_view(
                dsd.derived_series, '+localpackagediffs', method='GET',
                query_string='field.packageset=%d&field.packageset=%d' % (
                    packageset1.id, packageset2.id))
            self.assertContentEqual(
                [packageset1, packageset2],
                view.specified_packagesets_filter)

    def test_search_for_packagesets(self):
        # If packagesets are supplied in the query the resulting batch will
        # only contain packages in the given packagesets.
        dsd = self.factory.makeDistroSeriesDifference()
        person = dsd.derived_series.owner
        packageset = self.factory.makePackageset(
            owner=person, distroseries=dsd.derived_series)
        # The package is not in the packageset so the batch will be empty.
        with person_logged_in(person):
            view = create_initialized_view(
                dsd.derived_series, '+localpackagediffs', method='GET',
                query_string='field.packageset=%d' % packageset.id)
            self.assertEqual(0, len(view.cached_differences.batch))
            # The batch will contain the package once it has been added to the
            # packageset.
            packageset.add((dsd.source_package_name,))
            view = create_initialized_view(
                dsd.derived_series, '+localpackagediffs', method='GET',
                query_string='field.packageset=%d' % packageset.id)
            self.assertEqual(1, len(view.cached_differences.batch))

    def test_specified_changed_by_filter_none_specified(self):
        # specified_changed_by_filter is None when there are no
        # field.changed_by parameters in the query.
        dsd = self.factory.makeDistroSeriesDifference()
        person = dsd.derived_series.owner
        with person_logged_in(person):
            view = create_initialized_view(
                dsd.derived_series, '+localpackagediffs', method='GET',
                query_string='')
            self.assertIs(None, view.specified_changed_by_filter)

    def test_specified_changed_by_filter_specified(self):
        # specified_changed_by_filter returns a collection of Person when
        # there are field.changed_by query parameters.
        dsd = self.factory.makeDistroSeriesDifference()
        person = dsd.derived_series.owner
        changed_by1 = self.factory.makePerson()
        changed_by2 = self.factory.makePerson()
        with person_logged_in(person):
            query_string = urlencode(
                {"field.changed_by": (changed_by1.name, changed_by2.name)},
                doseq=True)
            view = create_initialized_view(
                dsd.derived_series, '+localpackagediffs', method='GET',
                query_string=query_string)
            self.assertContentEqual(
                [changed_by1, changed_by2],
                view.specified_changed_by_filter)

    def test_search_for_changed_by(self):
        # If changed_by is specified the query the resulting batch will only
        # contain packages relating to those people or teams.
        dsd = self.factory.makeDistroSeriesDifference()
        person = dsd.derived_series.owner
        ironhide = self.factory.makePersonByName("Ironhide")
        query_string = urlencode({"field.changed_by": ironhide.name})
        # The package release is not from Ironhide so the batch will be empty.
        with person_logged_in(person):
            view = create_initialized_view(
                dsd.derived_series, '+localpackagediffs', method='GET',
                query_string=query_string)
            self.assertEqual(0, len(view.cached_differences.batch))
            # The batch will contain the package once Ironhide has been
            # associated with its release.
            removeSecurityProxy(dsd.source_package_release).creator = ironhide
            view = create_initialized_view(
                dsd.derived_series, '+localpackagediffs', method='GET',
                query_string=query_string)
            self.assertEqual(1, len(view.cached_differences.batch))


class TestCopyAsynchronouslyMessage(TestCaseWithFactory):
    """Test the helper function `copy_asynchronously_message`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestCopyAsynchronouslyMessage, self).setUp()
        self.archive = self.factory.makeArchive()
        self.series = self.factory.makeDistroSeries()
        self.series_url = canonical_url(self.series)
        self.series_title = self.series.displayname

    def message(self, source_pubs_count):
        return copy_asynchronously_message(
            source_pubs_count, self.archive, dest_url=self.series_url,
            dest_display_name=self.series_title)

    def test_zero_packages(self):
        self.assertEqual(
            'Requested sync of 0 packages to <a href="%s">%s</a>.' %
                (self.series_url, self.series_title),
            self.message(0).escapedtext)

    def test_one_package(self):
        self.assertEqual(
            'Requested sync of 1 package to <a href="%s">%s</a>.<br />'
            'Please allow some time for this to be processed.' %
                (self.series_url, self.series_title),
            self.message(1).escapedtext)

    def test_multiple_packages(self):
        self.assertEqual(
            'Requested sync of 5 packages to <a href="%s">%s</a>.<br />'
            'Please allow some time for these to be processed.' %
                (self.series_url, self.series_title),
            self.message(5).escapedtext)


class TestDistroSeriesNeedsPackagesView(TestCaseWithFactory):
    """Test the distroseries +needs-packaging view."""

    layer = LaunchpadZopelessLayer

    def test_cached_unlinked_packages(self):
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        distroseries = self.factory.makeDistroSeries(distribution=ubuntu)
        view = create_initialized_view(distroseries, '+needs-packaging')
        self.assertTrue(
            IResultSet.providedBy(
                view.cached_unlinked_packages.currentBatch().list),
            '%s should batch IResultSet so that slicing will limit the '
            'query' % view.cached_unlinked_packages.currentBatch().list)


class DistroSeriesMissingPackageDiffsTestCase(TestCaseWithFactory):
    """Test the distroseries +missingpackages view."""

    layer = LaunchpadZopelessLayer

    def test_missingpackages_differences(self):
        # The view fetches the differences with type
        # MISSING_FROM_DERIVED_SERIES.
        dsp = self.factory.makeDistroSeriesParent()
        derived_series = dsp.derived_series

        missing_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        # Missing blacklisted diff.
        self.factory.makeDistroSeriesDifference(
            difference_type=missing_type,
            derived_series=derived_series,
            status=DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT)

        missing_diff = self.factory.makeDistroSeriesDifference(
            difference_type=missing_type,
            derived_series=derived_series,
            status=DistroSeriesDifferenceStatus.NEEDS_ATTENTION)

        view = create_initialized_view(
            derived_series, '+missingpackages')

        self.assertContentEqual(
            [missing_diff], view.cached_differences.batch)

    def test_missingpackages_differences_empty(self):
        # The view is empty if there is no differences with type
        # MISSING_FROM_DERIVED_SERIES.
        dsp = self.factory.makeDistroSeriesParent()
        derived_series = dsp.derived_series

        not_missing_type = DistroSeriesDifferenceType.DIFFERENT_VERSIONS

        # Missing diff.
        self.factory.makeDistroSeriesDifference(
            difference_type=not_missing_type,
            derived_series=derived_series,
            status=DistroSeriesDifferenceStatus.NEEDS_ATTENTION)

        view = create_initialized_view(
            derived_series, '+missingpackages')

        self.assertContentEqual(
            [], view.cached_differences.batch)

    def test_isNewerThanParent_is_False_if_missing_from_child(self):
        # If a package is missing from the child series,
        # isNewerThanParent returns False.
        missing_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        dsd = self.factory.makeDistroSeriesDifference(
            difference_type=missing_type)
        view = create_initialized_view(dsd.derived_series, '+missingpackages')
        self.assertFalse(view.isNewerThanParent(dsd))


class DistroSeriesMissingPackagesPageTestCase(TestCaseWithFactory,
                                              DistroSeriesDifferenceMixin):
    """Test the distroseries +missingpackages page."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(DistroSeriesMissingPackagesPageTestCase,
              self).setUp('foo.bar@canonical.com')
        self.simple_user = self.factory.makePerson()

    def test_parent_packagesets_missingpackages(self):
        # +missingpackages displays the packagesets in the parent.
        missing_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        self.ds_diff = self.factory.makeDistroSeriesDifference(
            difference_type=missing_type)

        with celebrity_logged_in('admin'):
            ps = self.factory.makePackageset(
                packages=[self.ds_diff.source_package_name],
                distroseries=self.ds_diff.parent_series)

        with person_logged_in(self.simple_user):
            view = create_initialized_view(
                self.ds_diff.derived_series,
                '+missingpackages',
                principal=self.simple_user)
            html_content = view()

        packageset_text = re.compile('\s*' + ps.name)
        self._test_packagesets(
            html_content, packageset_text, 'parent-packagesets',
            'Parent packagesets')

    def test_diff_row_last_changed(self):
        # The parent SPR creator (i.e. who make the package change, rather
        # than the uploader) is shown on each difference row.
        missing_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        dsd = self.factory.makeDistroSeriesDifference(
            difference_type=missing_type)
        with person_logged_in(self.simple_user):
            view = create_initialized_view(
                dsd.derived_series, '+missingpackages',
                principal=self.simple_user)
            root = html.fromstring(view())
        [creator_cell] = root.cssselect(
            "table.listing tbody td.last-changed")
        matches = DocTestMatches(
            "... ago by %s" % (
                dsd.parent_source_package_release.creator.displayname,))
        self.assertThat(creator_cell.text_content(), matches)

    def test_diff_row_last_changed_also_shows_uploader_if_different(self):
        # When the SPR creator and uploader are different both are named on
        # each difference row.
        missing_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        dsd = self.factory.makeDistroSeriesDifference(
            difference_type=missing_type)
        uploader = self.factory.makePerson()
        naked_spr = removeSecurityProxy(dsd.parent_source_package_release)
        naked_spr.dscsigningkey = self.factory.makeGPGKey(uploader)
        with person_logged_in(self.simple_user):
            view = create_initialized_view(
                dsd.derived_series, '+missingpackages',
                principal=self.simple_user)
            root = html.fromstring(view())
        [creator_cell] = root.cssselect(
            "table.listing tbody td.last-changed")
        parent_spr = dsd.parent_source_package_release
        matches = DocTestMatches(
            "... ago by %s (uploaded by %s)" % (
                parent_spr.creator.displayname,
                parent_spr.dscsigningkey.owner.displayname))
        self.assertThat(creator_cell.text_content(), matches)


class DistroSerieUniquePackageDiffsTestCase(TestCaseWithFactory,
                                            DistroSeriesDifferenceMixin):
    """Test the distroseries +uniquepackages view."""

    layer = LaunchpadZopelessLayer

    def test_uniquepackages_differences(self):
        # The view fetches the differences with type
        # UNIQUE_TO_DERIVED_SERIES.
        derived_series, parent_series = self._createChildAndParent()

        missing_type = DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES
        # Missing blacklisted diff.
        self.factory.makeDistroSeriesDifference(
            difference_type=missing_type,
            derived_series=derived_series,
            status=DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT)

        missing_diff = self.factory.makeDistroSeriesDifference(
            difference_type=missing_type,
            derived_series=derived_series,
            status=DistroSeriesDifferenceStatus.NEEDS_ATTENTION)

        view = create_initialized_view(
            derived_series, '+uniquepackages')

        self.assertContentEqual(
            [missing_diff], view.cached_differences.batch)

    def test_uniquepackages_displays_parent(self):
        # For a series derived from multiple parents, the parent for each
        # DSD is displayed; no parent version is displayed because we're
        # listing packages unique to the derived series.
        derived_series, parent_series = self._createChildAndParents()
        missing_type = DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES
        self.factory.makeDistroSeriesDifference(
            difference_type=missing_type,
            derived_series=derived_series,
            parent_series=parent_series,
            status=DistroSeriesDifferenceStatus.NEEDS_ATTENTION)
        view = create_initialized_view(
            derived_series, '+uniquepackages')

        multiple_parents_display_matcher = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                "Parent table header", 'th',
                text=re.compile("^\s*Parent\s")),
            Not(soupmatchers.Tag(
                "Parent version table header", 'th',
                text=re.compile("\s*Parent version\s*"))),
            soupmatchers.Tag(
                "Parent name", 'a',
                attrs={'class': 'parent-name'},
                text=re.compile("\s*%s\s*" % parent_series.displayname)),
             )
        self.assertThat(view.render(), multiple_parents_display_matcher)

    def test_uniquepackages_differences_empty(self):
        # The view is empty if there is no differences with type
        # UNIQUE_TO_DERIVED_SERIES.
        derived_series, parent_series = self._createChildAndParent()

        not_missing_type = DistroSeriesDifferenceType.DIFFERENT_VERSIONS

        # Missing diff.
        self.factory.makeDistroSeriesDifference(
            difference_type=not_missing_type,
            derived_series=derived_series,
            status=DistroSeriesDifferenceStatus.NEEDS_ATTENTION)

        view = create_initialized_view(
            derived_series, '+uniquepackages')

        self.assertContentEqual(
            [], view.cached_differences.batch)

    def test_isNewerThanParent_is_True_if_unique_to_child(self):
        unique_to_child = DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES
        dsd = self.factory.makeDistroSeriesDifference(
            difference_type=unique_to_child)
        view = create_initialized_view(
            dsd.derived_series, '+localpackagediffs')
        self.assertTrue(view.isNewerThanParent(dsd))


class DistroSeriesUniquePackagesPageTestCase(TestCaseWithFactory,
                                             DistroSeriesDifferenceMixin):
    """Test the distroseries +uniquepackages page."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(DistroSeriesUniquePackagesPageTestCase,
              self).setUp('foo.bar@canonical.com')
        self.simple_user = self.factory.makePerson()

    def test_packagesets_uniquepackages(self):
        # +uniquepackages displays the packagesets in the parent.
        missing_type = DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES
        self.ds_diff = self.factory.makeDistroSeriesDifference(
            difference_type=missing_type)

        with celebrity_logged_in('admin'):
            ps = self.factory.makePackageset(
                packages=[self.ds_diff.source_package_name],
                distroseries=self.ds_diff.derived_series)

        with person_logged_in(self.simple_user):
            view = create_initialized_view(
                self.ds_diff.derived_series,
                '+uniquepackages',
                principal=self.simple_user)
            html = view()

        packageset_text = re.compile('\s*' + ps.name)
        self._test_packagesets(
            html, packageset_text, 'packagesets', 'Packagesets')


class TestDistroSeriesEditView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_edit_full_functionality_sets_datereleased(self):
        # Full functionality distributions (IE: Ubuntu) have datereleased
        # set when the +edit view is used.
        ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
        distroseries = self.factory.makeDistroSeries(distribution=ubuntu)
        form = {
            'field.actions.change': 'Change',
            'field.status': 'CURRENT'
            }
        admin = login_celebrity('admin')
        create_initialized_view(
            distroseries, name='+edit', principal=admin, form=form)
        self.assertIsNot(None, distroseries.datereleased)
