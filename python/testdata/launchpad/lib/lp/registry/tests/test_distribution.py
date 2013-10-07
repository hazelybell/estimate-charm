# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for Distribution."""

__metaclass__ = type

import datetime

from fixtures import FakeLogger
from lazr.lifecycle.snapshot import Snapshot
import pytz
import soupmatchers
from storm.store import Store
from testtools import ExpectedException
from testtools.matchers import (
    MatchesAll,
    MatchesAny,
    Not,
    )
import transaction
from zope.component import getUtility
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import (
    InformationType,
    ServiceUsage,
    )
from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.enums import (
    BranchSharingPolicy,
    BugSharingPolicy,
    EXCLUSIVE_TEAM_POLICY,
    INCLUSIVE_TEAM_POLICY,
    )
from lp.registry.errors import (
    InclusiveTeamLinkageError,
    NoSuchDistroSeries,
    )
from lp.registry.interfaces.accesspolicy import IAccessPolicySource
from lp.registry.interfaces.distribution import (
    IDistribution,
    IDistributionSet,
    )
from lp.registry.interfaces.oopsreferences import IHasOOPSReferences
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.tests.test_distroseries import CurrentSourceReleasesMixin
from lp.services.propertycache import get_property_cache
from lp.services.webapp import canonical_url
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.interfaces.distributionsourcepackagerelease import (
    IDistributionSourcePackageRelease,
    )
from lp.testing import (
    celebrity_logged_in,
    login_person,
    person_logged_in,
    TestCase,
    TestCaseWithFactory,
    WebServiceTestCase,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    ZopelessDatabaseLayer,
    )
from lp.testing.matchers import Provides
from lp.testing.views import create_initialized_view
from lp.translations.enums import TranslationPermission


class TestDistribution(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_pillar_category(self):
        # The pillar category is correct.
        distro = self.factory.makeDistribution()
        self.assertEqual("Distribution", distro.pillar_category)

    def test_sharing_policies(self):
        # The sharing policies are PUBLIC.
        distro = self.factory.makeDistribution()
        self.assertEqual(
            BranchSharingPolicy.PUBLIC, distro.branch_sharing_policy)
        self.assertEqual(
            BugSharingPolicy.PUBLIC, distro.bug_sharing_policy)

    def test_owner_cannot_be_open_team(self):
        """Distro owners cannot be open teams."""
        for policy in INCLUSIVE_TEAM_POLICY:
            open_team = self.factory.makeTeam(membership_policy=policy)
            self.assertRaises(
                InclusiveTeamLinkageError, self.factory.makeDistribution,
                owner=open_team)

    def test_owner_can_be_closed_team(self):
        """Distro owners can be exclusive teams."""
        for policy in EXCLUSIVE_TEAM_POLICY:
            closed_team = self.factory.makeTeam(membership_policy=policy)
            self.factory.makeDistribution(owner=closed_team)

    def test_distribution_repr_ansii(self):
        # Verify that ANSI displayname is ascii safe.
        distro = self.factory.makeDistribution(
            name="distro", displayname=u'\xdc-distro')
        ignore, displayname, name = repr(distro).rsplit(' ', 2)
        self.assertEqual("'\\xdc-distro'", displayname)
        self.assertEqual('(distro)>', name)

    def test_distribution_repr_unicode(self):
        # Verify that Unicode displayname is ascii safe.
        distro = self.factory.makeDistribution(
            name="distro", displayname=u'\u0170-distro')
        ignore, displayname, name = repr(distro).rsplit(' ', 2)
        self.assertEqual("'\\u0170-distro'", displayname)

    def test_guessPublishedSourcePackageName_no_distro_series(self):
        # Distribution without a series raises NotFoundError
        distro = self.factory.makeDistribution()
        with ExpectedException(NotFoundError, '.*has no series.*'):
            distro.guessPublishedSourcePackageName('package')

    def test_guessPublishedSourcePackageName_invalid_name(self):
        # Invalid name raises a NotFoundError
        distro = self.factory.makeDistribution()
        with ExpectedException(NotFoundError, "'Invalid package name.*"):
            distro.guessPublishedSourcePackageName('a*package')

    def test_guessPublishedSourcePackageName_nothing_published(self):
        distroseries = self.factory.makeDistroSeries()
        with ExpectedException(NotFoundError, "'Unknown package:.*"):
            distroseries.distribution.guessPublishedSourcePackageName(
                'a-package')

    def test_guessPublishedSourcePackageName_ignored_removed(self):
        # Removed binary package are ignored.
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeBinaryPackagePublishingHistory(
            archive=distroseries.main_archive,
            binarypackagename='binary-package',
            status=PackagePublishingStatus.SUPERSEDED)
        with ExpectedException(NotFoundError, ".*Binary package.*"):
            distroseries.distribution.guessPublishedSourcePackageName(
                'binary-package')

    def test_guessPublishedSourcePackageName_sourcepackage_name(self):
        distroseries = self.factory.makeDistroSeries()
        spph = self.factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries, sourcepackagename='my-package')
        self.assertEquals(
            spph.sourcepackagerelease.sourcepackagename,
            distroseries.distribution.guessPublishedSourcePackageName(
                'my-package'))

    def test_guessPublishedSourcePackageName_binarypackage_name(self):
        distroseries = self.factory.makeDistroSeries()
        spph = self.factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries, sourcepackagename='my-package')
        self.factory.makeBinaryPackagePublishingHistory(
            archive=distroseries.main_archive,
            binarypackagename='binary-package',
            source_package_release=spph.sourcepackagerelease)
        self.assertEquals(
            spph.sourcepackagerelease.sourcepackagename,
            distroseries.distribution.guessPublishedSourcePackageName(
                'binary-package'))

    def test_guessPublishedSourcePackageName_exlude_ppa(self):
        # Package published in PPAs are not considered to be part of the
        # distribution.
        distroseries = self.factory.makeUbuntuDistroSeries()
        ppa_archive = self.factory.makeArchive()
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries, sourcepackagename='my-package',
            archive=ppa_archive)
        with ExpectedException(NotFoundError, ".*not published in.*"):
            distroseries.distribution.guessPublishedSourcePackageName(
                'my-package')

    def test_guessPublishedSourcePackageName_exlude_other_distro(self):
        # Published source package are only found in the distro
        # in which they were published.
        distroseries1 = self.factory.makeDistroSeries()
        distroseries2 = self.factory.makeDistroSeries()
        spph = self.factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries1, sourcepackagename='my-package')
        self.assertEquals(
            spph.sourcepackagerelease.sourcepackagename,
            distroseries1.distribution.guessPublishedSourcePackageName(
                'my-package'))
        with ExpectedException(NotFoundError, ".*not published in.*"):
            distroseries2.distribution.guessPublishedSourcePackageName(
                'my-package')

    def test_guessPublishedSourcePackageName_looks_for_source_first(self):
        # If both a binary and source package name shares the same name,
        # the source package will be returned (and the one from the unrelated
        # binary).
        distroseries = self.factory.makeDistroSeries()
        my_spph = self.factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries, sourcepackagename='my-package')
        self.factory.makeBinaryPackagePublishingHistory(
            archive=distroseries.main_archive,
            binarypackagename='my-package', sourcepackagename='other-package')
        self.assertEquals(
            my_spph.sourcepackagerelease.sourcepackagename,
            distroseries.distribution.guessPublishedSourcePackageName(
                'my-package'))

    def test_guessPublishedSourcePackageName_uses_latest(self):
        # If multiple binaries match, it will return the source of the latest
        # one published.
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeBinaryPackagePublishingHistory(
            archive=distroseries.main_archive,
            sourcepackagename='old-source-name',
            binarypackagename='my-package')
        self.factory.makeBinaryPackagePublishingHistory(
            archive=distroseries.main_archive,
            sourcepackagename='new-source-name',
            binarypackagename='my-package')
        self.assertEquals(
            'new-source-name',
            distroseries.distribution.guessPublishedSourcePackageName(
                'my-package').name)

    def test_guessPublishedSourcePackageName_official_package_branch(self):
        # It consider that a sourcepackage that has an official package
        # branch is published.
        sourcepackage = self.factory.makeSourcePackage(
            sourcepackagename='my-package')
        self.factory.makeRelatedBranchesForSourcePackage(
            sourcepackage=sourcepackage)
        self.assertEquals(
            'my-package',
            sourcepackage.distribution.guessPublishedSourcePackageName(
                'my-package').name)

    def test_derivatives_email(self):
        # Make sure the package_derivatives_email column stores data
        # correctly.
        email = "thingy@foo.com"
        distro = self.factory.makeDistribution()
        with person_logged_in(distro.owner):
            distro.package_derivatives_email = email
        Store.of(distro).flush()
        self.assertEqual(email, distro.package_derivatives_email)

    def test_derivatives_email_permissions(self):
        # package_derivatives_email requires lp.edit to set/change.
        distro = self.factory.makeDistribution()
        self.assertRaises(
            Unauthorized,
            setattr, distro, "package_derivatives_email", "foo")

    def test_implements_interfaces(self):
        # Distribution fully implements its interfaces.
        distro = removeSecurityProxy(self.factory.makeDistribution())
        expected_interfaces = [
            IHasOOPSReferences,
            ]
        provides_all = MatchesAll(*map(Provides, expected_interfaces))
        self.assertThat(distro, provides_all)

    def test_distribution_creation_creates_accesspolicies(self):
        # Creating a new distribution also creates AccessPolicies for it.
        distro = self.factory.makeDistribution()
        ap = getUtility(IAccessPolicySource).findByPillar((distro,))
        expected = [
            InformationType.USERDATA, InformationType.PRIVATESECURITY]
        self.assertContentEqual(expected, [policy.type for policy in ap])

    def test_getAllowedBugInformationTypes(self):
        # All distros currently support just the non-proprietary
        # information types.
        self.assertContentEqual(
            [InformationType.PUBLIC, InformationType.PUBLICSECURITY,
             InformationType.PRIVATESECURITY, InformationType.USERDATA],
            self.factory.makeDistribution().getAllowedBugInformationTypes())

    def test_getDefaultBugInformationType(self):
        # The default information type for distributions is always PUBLIC.
        self.assertEqual(
            InformationType.PUBLIC,
            self.factory.makeDistribution().getDefaultBugInformationType())

    def test_getAllowedSpecificationInformationTypes(self):
        # All distros currently support only public specifications.
        distro = self.factory.makeDistribution()
        self.assertContentEqual(
            [InformationType.PUBLIC],
            distro.getAllowedSpecificationInformationTypes()
            )

    def test_getDefaultSpecificationInformtationType(self):
        # All distros currently support only Public by default
        # specifications.
        distro = self.factory.makeDistribution()
        self.assertEqual(
            InformationType.PUBLIC,
            distro.getDefaultSpecificationInformationType())


class TestDistributionCurrentSourceReleases(
    CurrentSourceReleasesMixin, TestCase):
    """Test for Distribution.getCurrentSourceReleases().

    This works in the same way as
    DistroSeries.getCurrentSourceReleases() works, except that we look
    for the latest published source across multiple distro series.
    """

    layer = LaunchpadFunctionalLayer
    release_interface = IDistributionSourcePackageRelease

    @property
    def target(self):
        return self.distribution

    def test_which_distroseries_does_not_matter(self):
        # When checking for the current release, we only care about the
        # version numbers. We don't care whether the version is
        # published in a earlier or later series.
        self.current_series = self.factory.makeDistroSeries(
            self.distribution, '1.0', status=SeriesStatus.CURRENT)
        self.publisher.getPubSource(
            version='0.9', distroseries=self.current_series)
        self.publisher.getPubSource(
            version='1.0', distroseries=self.development_series)
        self.assertCurrentVersion('1.0')

        self.publisher.getPubSource(
            version='1.1', distroseries=self.current_series)
        self.assertCurrentVersion('1.1')

    def test_distribution_series_cache(self):
        distribution = removeSecurityProxy(
            self.factory.makeDistribution('foo'))

        cache = get_property_cache(distribution)

        # Not yet cached.
        self.assertNotIn("series", cache)

        # Now cached.
        series = distribution.series
        self.assertIs(series, cache.series)

        # Cache cleared.
        distribution.newSeries(
            name='bar', displayname='Bar', title='Bar', summary='',
            description='', version='1', previous_series=None,
            registrant=self.factory.makePerson())
        self.assertNotIn("series", cache)

        # New cached value.
        series = distribution.series
        self.assertEqual(1, len(series))
        self.assertIs(series, cache.series)


class SeriesByStatusTests(TestCaseWithFactory):
    """Test IDistribution.getSeriesByStatus().
    """

    layer = LaunchpadFunctionalLayer

    def test_get_none(self):
        distro = self.factory.makeDistribution()
        self.assertEquals([],
            list(distro.getSeriesByStatus(SeriesStatus.FROZEN)))

    def test_get_current(self):
        distro = self.factory.makeDistribution()
        series = self.factory.makeDistroSeries(distribution=distro,
            status=SeriesStatus.CURRENT)
        self.assertEquals([series],
            list(distro.getSeriesByStatus(SeriesStatus.CURRENT)))


class SeriesTests(TestCaseWithFactory):
    """Test IDistribution.getSeries().
    """

    layer = LaunchpadFunctionalLayer

    def test_get_none(self):
        distro = self.factory.makeDistribution()
        self.assertRaises(NoSuchDistroSeries, distro.getSeries, "astronomy")

    def test_get_by_name(self):
        distro = self.factory.makeDistribution()
        series = self.factory.makeDistroSeries(distribution=distro,
            name="dappere")
        self.assertEquals(series, distro.getSeries("dappere"))

    def test_get_by_version(self):
        distro = self.factory.makeDistribution()
        series = self.factory.makeDistroSeries(distribution=distro,
            name="dappere", version="42.6")
        self.assertEquals(series, distro.getSeries("42.6"))

    def test_development_series_alias(self):
        distro = self.factory.makeDistribution()
        with person_logged_in(distro.owner):
            distro.development_series_alias = "devel"
        self.assertRaises(
            NoSuchDistroSeries, distro.getSeries, "devel", follow_aliases=True)
        series = self.factory.makeDistroSeries(
            distribution=distro, status=SeriesStatus.DEVELOPMENT)
        self.assertRaises(NoSuchDistroSeries, distro.getSeries, "devel")
        self.assertEqual(
            series, distro.getSeries("devel", follow_aliases=True))


class DerivativesTests(TestCaseWithFactory):
    """Test IDistribution.derivatives.
    """

    layer = LaunchpadFunctionalLayer

    def test_derivatives(self):
        distro1 = self.factory.makeDistribution()
        distro2 = self.factory.makeDistribution()
        previous_series = self.factory.makeDistroSeries(distribution=distro1)
        series = self.factory.makeDistroSeries(
            distribution=distro2, previous_series=previous_series)
        self.assertContentEqual([series], distro1.derivatives)


class DistroSnapshotTestCase(TestCaseWithFactory):
    """A TestCase for distribution snapshots."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(DistroSnapshotTestCase, self).setUp()
        self.distribution = self.factory.makeDistribution(name="boobuntu")

    def test_snapshot(self):
        """Snapshots of distributions should not include marked attribues.

        Wrap an export with 'doNotSnapshot' to force the snapshot to not
        include that attribute.
        """
        snapshot = Snapshot(self.distribution, providing=IDistribution)
        omitted = [
            'archive_mirrors',
            'cdimage_mirrors',
            'series',
            'all_distro_archives',
            ]
        for attribute in omitted:
            self.assertFalse(
                hasattr(snapshot, attribute),
                "Snapshot should not include %s." % attribute)


class TestDistributionPage(TestCaseWithFactory):
    """A TestCase for the distribution page."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistributionPage, self).setUp('foo.bar@canonical.com')
        self.distro = self.factory.makeDistribution(
            name="distro", displayname=u'distro')
        self.admin = getUtility(IPersonSet).getByEmail(
            'admin@canonical.com')
        self.simple_user = self.factory.makePerson()
        # Use a FakeLogger fixture to prevent Memcached warnings to be
        # printed to stdout while browsing pages.
        self.useFixture(FakeLogger())

    def test_distributionpage_addseries_link(self):
        """ Verify that an admin sees the +addseries link."""
        login_person(self.admin)
        view = create_initialized_view(
            self.distro, '+index', principal=self.admin)
        series_matches = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'link to add a series', 'a',
                attrs={'href':
                    canonical_url(self.distro, view_name='+addseries')},
                text='Add series'),
            soupmatchers.Tag(
                'Active series and milestones widget', 'h2',
                text='Active series and milestones'),
            )
        self.assertThat(view.render(), series_matches)

    def test_distributionpage_addseries_link_noadmin(self):
        """Verify that a non-admin does not see the +addseries link
        nor the series header (since there is no series yet).
        """
        login_person(self.simple_user)
        view = create_initialized_view(
            self.distro, '+index', principal=self.simple_user)
        add_series_match = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'link to add a series', 'a',
                attrs={'href':
                    canonical_url(self.distro, view_name='+addseries')},
                text='Add series'))
        series_header_match = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Active series and milestones widget', 'h2',
                text='Active series and milestones'))
        self.assertThat(
            view.render(),
            Not(MatchesAny(add_series_match, series_header_match)))

    def test_distributionpage_series_list_noadmin(self):
        """Verify that a non-admin does see the series list
        when there is a series.
        """
        self.factory.makeDistroSeries(distribution=self.distro,
            status=SeriesStatus.CURRENT)
        login_person(self.simple_user)
        view = create_initialized_view(
            self.distro, '+index', principal=self.simple_user)
        add_series_match = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'link to add a series', 'a',
                attrs={'href':
                    canonical_url(self.distro, view_name='+addseries')},
                text='Add series'))
        series_header_match = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Active series and milestones widget', 'h2',
                text='Active series and milestones'))
        self.assertThat(view.render(), series_header_match)
        self.assertThat(view.render(), Not(add_series_match))


class DistroRegistrantTestCase(TestCaseWithFactory):
    """A TestCase for registrants and owners of a distribution.

    The registrant is the creator of the distribution (read-only field).
    The owner is really the maintainer.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(DistroRegistrantTestCase, self).setUp()
        self.owner = self.factory.makePerson()
        self.registrant = self.factory.makePerson()

    def test_distro_registrant_owner_differ(self):
        distribution = self.factory.makeDistribution(
            name="boobuntu", owner=self.owner, registrant=self.registrant)
        self.assertNotEqual(distribution.owner, distribution.registrant)
        self.assertEqual(distribution.owner, self.owner)
        self.assertEqual(distribution.registrant, self.registrant)


class DistributionSet(TestCaseWithFactory):
    """Test case for `IDistributionSet`."""

    layer = ZopelessDatabaseLayer

    def test_implements_interface(self):
        self.assertThat(
            getUtility(IDistributionSet), Provides(IDistributionSet))

    def test_getDerivedDistributions_finds_derived_distro(self):
        dsp = self.factory.makeDistroSeriesParent()
        derived_distro = dsp.derived_series.distribution
        distroset = getUtility(IDistributionSet)
        self.assertIn(derived_distro, distroset.getDerivedDistributions())

    def test_getDerivedDistributions_ignores_nonderived_distros(self):
        distroset = getUtility(IDistributionSet)
        nonderived_distro = self.factory.makeDistribution()
        self.assertNotIn(
            nonderived_distro, distroset.getDerivedDistributions())

    def test_getDerivedDistributions_ignores_ubuntu_even_if_derived(self):
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        self.factory.makeDistroSeriesParent(
            derived_series=ubuntu.currentseries)
        distroset = getUtility(IDistributionSet)
        self.assertNotIn(ubuntu, distroset.getDerivedDistributions())

    def test_getDerivedDistribution_finds_each_distro_just_once(self):
        # Derived distros are not duplicated in the output of
        # getDerivedDistributions, even if they have multiple parents and
        # multiple derived series.
        dsp = self.factory.makeDistroSeriesParent()
        distro = dsp.derived_series.distribution
        other_series = self.factory.makeDistroSeries(distribution=distro)
        self.factory.makeDistroSeriesParent(derived_series=other_series)
        distroset = getUtility(IDistributionSet)
        self.assertEqual(1, len(list(distroset.getDerivedDistributions())))


class TestDistributionTranslations(TestCaseWithFactory):
    """A TestCase for accessing distro translations-related attributes."""

    layer = DatabaseFunctionalLayer

    def test_rosetta_expert(self):
        # Ensure rosetta-experts can set Distribution attributes
        # related to translations.
        distro = self.factory.makeDistribution()
        new_series = self.factory.makeDistroSeries(distribution=distro)
        group = self.factory.makeTranslationGroup()
        with celebrity_logged_in('rosetta_experts'):
            distro.translations_usage = ServiceUsage.LAUNCHPAD
            distro.translation_focus = new_series
            distro.translationgroup = group
            distro.translationpermission = TranslationPermission.CLOSED

    def test_translation_group_owner(self):
        # Ensure TranslationGroup owner for a Distribution can modify
        # all attributes related to distribution translations.
        distro = self.factory.makeDistribution()
        new_series = self.factory.makeDistroSeries(distribution=distro)
        group = self.factory.makeTranslationGroup()
        with celebrity_logged_in('admin'):
            distro.translationgroup = group

        new_group = self.factory.makeTranslationGroup()
        with person_logged_in(group.owner):
            distro.translations_usage = ServiceUsage.LAUNCHPAD
            distro.translation_focus = new_series
            distro.translationgroup = new_group
            distro.translationpermission = TranslationPermission.CLOSED


class TestWebService(WebServiceTestCase):

    def test_oops_references_matching_distro(self):
        # The distro layer provides the context restriction, so we need to
        # check we can access context filtered references - e.g. on question.
        oopsid = "OOPS-abcdef1234"
        distro = self.factory.makeDistribution()
        self.factory.makeQuestion(
            title="Crash with %s" % oopsid, target=distro)
        transaction.commit()
        ws_distro = self.wsObject(distro, distro.owner)
        now = datetime.datetime.now(tz=pytz.utc)
        day = datetime.timedelta(days=1)
        self.failUnlessEqual(
            [oopsid],
            ws_distro.findReferencedOOPS(start_date=now - day, end_date=now))
        self.failUnlessEqual(
            [],
            ws_distro.findReferencedOOPS(
                start_date=now + day, end_date=now + day))

    def test_oops_references_different_distro(self):
        # The distro layer provides the context restriction, so we need to
        # check the filter is tight enough - other contexts should not work.
        oopsid = "OOPS-abcdef1234"
        self.factory.makeQuestion(title="Crash with %s" % oopsid)
        distro = self.factory.makeDistribution()
        transaction.commit()
        ws_distro = self.wsObject(distro, distro.owner)
        now = datetime.datetime.now(tz=pytz.utc)
        day = datetime.timedelta(days=1)
        self.failUnlessEqual(
            [],
            ws_distro.findReferencedOOPS(start_date=now - day, end_date=now))
