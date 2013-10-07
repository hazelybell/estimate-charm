# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests relating to the revision cache."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

import pytz
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.code.interfaces.revisioncache import IRevisionCache
from lp.code.model.revision import RevisionCache
from lp.services.database.interfaces import IStore
from lp.testing import (
    TestCaseWithFactory,
    time_counter,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestRevisionCacheAdaptation(TestCaseWithFactory):
    """Check that certain objects can be adapted to a revision cache."""

    layer = DatabaseFunctionalLayer

    def test_product(self):
        # A product can be adapted to a revision cache.
        product = self.factory.makeProduct()
        cache = IRevisionCache(product, None)
        self.assertIsNot(None, cache)

    def test_project(self):
        # A project can be adapted to a revision cache.
        project = self.factory.makeProject()
        cache = IRevisionCache(project, None)
        self.assertIsNot(None, cache)

    def test_person(self):
        # A person can be adapted to a revision cache.
        person = self.factory.makePerson()
        cache = IRevisionCache(person, None)
        self.assertIsNot(None, cache)

    def test_distribution(self):
        # A distribution can be adapted to a revision cache.
        distribution = self.factory.makeDistribution()
        cache = IRevisionCache(distribution, None)
        self.assertIsNot(None, cache)

    def test_distro_series(self):
        # A distro series can be adapted to a revision cache.
        distro_series = self.factory.makeDistroSeries()
        cache = IRevisionCache(distro_series, None)
        self.assertIsNot(None, cache)

    def test_source_package(self):
        # A source package can be adapted to a revision cache.
        source_package = self.factory.makeSourcePackage()
        cache = IRevisionCache(source_package, None)
        self.assertIsNot(None, cache)

    def test_distribution_source__package(self):
        # A distribution source pakcage can be adapted to a revision cache.
        distro_source_package = self.factory.makeDistributionSourcePackage()
        cache = IRevisionCache(distro_source_package, None)
        self.assertIsNot(None, cache)


class TestRevisionCache(TestCaseWithFactory):
    """Test the revision cache filters and counts."""

    layer = DatabaseFunctionalLayer

    def test_initially_empty(self):
        # A test just to confirm that the RevisionCache is empty.
        results = IStore(RevisionCache).find(RevisionCache)
        self.assertEqual(0, results.count())

    def makeCachedRevision(self, revision=None, product=None,
                           package=None, private=False):
        # A factory method for RevisionCache objects.
        if revision is None:
            revision = self.factory.makeRevision()
        cached = RevisionCache(revision)
        cached.product = product
        if package is not None:
            cached.distroseries = package.distroseries
            cached.sourcepackagename = package.sourcepackagename
        cached.private = private
        return revision

    def test_simple_total_count(self):
        # Test that the count does in fact count the revisions we add.
        for i in range(4):
            self.makeCachedRevision()
        cache = getUtility(IRevisionCache)
        self.assertEqual(4, cache.count())

    def test_revision_ordering(self):
        # Revisions are returned most recent first.
        tc = time_counter(
            origin=datetime.now(pytz.UTC) - timedelta(days=15),
            delta=timedelta(days=1))
        # Make four cached revisions spanning 15, 14, 13 and 12 days ago.
        # Create from oldest to newest, then check that the ordering from the
        # query is the reverse order.
        revisions = [
            self.makeCachedRevision(
                revision=self.factory.makeRevision(revision_date=tc.next()))
            for i in range(4)]
        revisions.reverse()
        cache = getUtility(IRevisionCache)
        self.assertEqual(revisions, list(cache.getRevisions()))

    def test_revision_in_multiple_namespaces_counted_once(self):
        # A revision that is in multiple namespaces is only counted once.
        revision = self.factory.makeRevision()
        # Make a cached revision of a revision in a junk branch.
        self.makeCachedRevision(revision)
        # Make the same revision appear in a product.
        self.makeCachedRevision(revision, product=self.factory.makeProduct())
        # And the same revision in a source package.
        self.makeCachedRevision(
            revision, package=self.factory.makeSourcePackage())
        cache = getUtility(IRevisionCache)
        self.assertEqual(1, cache.count())

    def test_revisions_bound_by_date(self):
        # Only revisions in the last 30 days are returned, even if the
        # revision cache table hasn't been trimmed lately.
        tc = time_counter(
            origin=datetime.now(pytz.UTC) - timedelta(days=27),
            delta=timedelta(days=-2))
        # Make four cached revisions spanning 33, 31, 29, and 27 days ago.
        for i in range(4):
            self.makeCachedRevision(
                revision=self.factory.makeRevision(revision_date=tc.next()))
        cache = getUtility(IRevisionCache)
        self.assertEqual(2, cache.count())

    def assertCollectionContents(self, expected_revisions,
                                 revision_collection):
        # Check that the revisions returned from the revision collection match
        # the expected revisions.
        self.assertEqual(
            sorted(expected_revisions),
            sorted(revision_collection.getRevisions()))

    def test_private_revisions(self):
        # Private flags are honoured when only requesting public revisions.
        # If a revision is in both public and private branches, then there are
        # two entried in the revision cache for it, and it will be retrieved
        # in a revision query
        revision = self.factory.makeRevision()
        # Put that revision in both a public and private branch.
        self.makeCachedRevision(revision, private=False)
        self.makeCachedRevision(revision, private=True)
        # Make a random public cached revision.
        public_revision = self.makeCachedRevision()
        # Make a private cached revision.
        self.makeCachedRevision(private=True)

        cache = getUtility(IRevisionCache)
        # Counting all revisions gets public and private revisions.
        self.assertEqual(3, cache.count())
        # Limiting to public revisions does not get the private revisions.
        self.assertEqual(2, cache.public().count())
        self.assertCollectionContents(
            [revision, public_revision], cache.public())

    def test_in_product(self):
        # Revisions in a particular product can be restricted using the
        # inProduct method.
        product = self.factory.makeProduct()
        rev1 = self.makeCachedRevision(product=product)
        rev2 = self.makeCachedRevision(product=product)
        # Make two other revisions, on in a different product, and another
        # general one.
        self.makeCachedRevision(product=self.factory.makeProduct())
        self.makeCachedRevision()
        revision_cache = getUtility(IRevisionCache).inProduct(product)
        self.assertCollectionContents([rev1, rev2], revision_cache)

    def test_in_project(self):
        # Revisions across a project group can be determined using the
        # inProject method.
        project = self.factory.makeProject()
        product1 = self.factory.makeProduct(project=project)
        product2 = self.factory.makeProduct(project=project)
        rev1 = self.makeCachedRevision(product=product1)
        rev2 = self.makeCachedRevision(product=product2)
        # Make two other revisions, on in a different product, and another
        # general one.
        self.makeCachedRevision(product=self.factory.makeProduct())
        self.makeCachedRevision()
        revision_cache = getUtility(IRevisionCache).inProject(project)
        self.assertCollectionContents([rev1, rev2], revision_cache)

    def test_in_source_package(self):
        # Revisions associated with a particular source package are available
        # using the inSourcePackage method.
        sourcepackage = self.factory.makeSourcePackage()
        rev1 = self.makeCachedRevision(package=sourcepackage)
        rev2 = self.makeCachedRevision(package=sourcepackage)
        # Make two other revisions, on in a different product, and another
        # general one.
        self.makeCachedRevision(package=self.factory.makeSourcePackage())
        self.makeCachedRevision()
        revision_cache = getUtility(IRevisionCache).inSourcePackage(
            sourcepackage)
        self.assertCollectionContents([rev1, rev2], revision_cache)

    def test_in_distribution(self):
        # Check inDistribution limits to those revisions associated with
        # distribution series related to the distro.
        distroseries1 = self.factory.makeDistroSeries()
        distro = distroseries1.distribution
        distroseries2 = self.factory.makeDistroSeries(distribution=distro)
        # Two revisions associated with sourcepackages in the series for the
        # distro.
        rev1 = self.makeCachedRevision(
            package=self.factory.makeSourcePackage(
                distroseries=distroseries1))
        rev2 = self.makeCachedRevision(
            package=self.factory.makeSourcePackage(
                distroseries=distroseries2))
        # Make two other revisions, on in a different product, and another
        # general one.
        self.makeCachedRevision(package=self.factory.makeSourcePackage())
        self.makeCachedRevision()
        revision_cache = getUtility(IRevisionCache).inDistribution(distro)
        self.assertCollectionContents([rev1, rev2], revision_cache)

    def test_in_distro_series(self):
        # Check that inDistroSeries limits the revisions to those in the
        # distroseries specified.
        distroseries1 = self.factory.makeDistroSeries()
        distro = distroseries1.distribution
        distroseries2 = self.factory.makeDistroSeries(distribution=distro)
        # Two revisions associated with sourcepackages in the distro series we
        # care about.
        rev1 = self.makeCachedRevision(
            package=self.factory.makeSourcePackage(
                distroseries=distroseries1))
        rev2 = self.makeCachedRevision(
            package=self.factory.makeSourcePackage(
                distroseries=distroseries1))
        # Make some other revisions.  Same distro, different series.
        self.makeCachedRevision(
            package=self.factory.makeSourcePackage(
                distroseries=distroseries2))
        # Different distro source package revision.
        self.makeCachedRevision(package=self.factory.makeSourcePackage())
        # Some other revision.
        self.makeCachedRevision()
        revision_cache = getUtility(IRevisionCache).inDistroSeries(
            distroseries1)
        self.assertCollectionContents([rev1, rev2], revision_cache)

    def test_in_distribution_source_package(self):
        # Check that inDistributionSourcePackage limits to revisions in
        # different distro series for the same source package name.
        distroseries1 = self.factory.makeDistroSeries()
        distro = distroseries1.distribution
        distroseries2 = self.factory.makeDistroSeries(distribution=distro)
        # Two revisions associated with the same sourcepackagename in the
        # distro series we care about.
        sourcepackagename = self.factory.makeSourcePackageName()
        rev1 = self.makeCachedRevision(
            package=self.factory.makeSourcePackage(
                distroseries=distroseries1,
                sourcepackagename=sourcepackagename))
        rev2 = self.makeCachedRevision(
            package=self.factory.makeSourcePackage(
                distroseries=distroseries2,
                sourcepackagename=sourcepackagename))
        # Make some other revisions.  Same distroseries, different source
        # package.
        self.makeCachedRevision(
            package=self.factory.makeSourcePackage(
                distroseries=distroseries1))
        # Different distro source package revision.
        self.makeCachedRevision(package=self.factory.makeSourcePackage())
        # Some other revision.
        self.makeCachedRevision()
        dsp = self.factory.makeDistributionSourcePackage(
            distribution=distro, sourcepackagename=sourcepackagename)
        revision_cache = getUtility(IRevisionCache)
        revision_cache = revision_cache.inDistributionSourcePackage(dsp)
        self.assertCollectionContents([rev1, rev2], revision_cache)

    def makePersonAndLinkedRevision(self):
        """Make a person and a revision that is linked to them."""
        person = self.factory.makePerson()
        revision = self.factory.makeRevision()
        # Link up the revision author and person.  This is normally a
        # protected method, so remove the security proxy.
        removeSecurityProxy(revision.revision_author).person = person
        rev = self.makeCachedRevision(revision)
        return person, rev

    def test_authored_by_individual(self):
        # Check that authoredBy appropriatly limits revisions to those
        # authored by the individual specified.
        eric, rev1 = self.makePersonAndLinkedRevision()
        # Make a second revision by eric.
        rev2 = self.makeCachedRevision(
            self.factory.makeRevision(rev1.revision_author.name))
        # Other revisions have other authors.
        self.makeCachedRevision()
        revision_cache = getUtility(IRevisionCache).authoredBy(eric)
        self.assertCollectionContents([rev1, rev2], revision_cache)

    def test_authored_by_team(self):
        # Check that authoredBy appropriatly limits revisions to those
        # authored by individuals of a team.  Since we want to add members to
        # the team, and don't want security checks, we remove the security
        # proxy from the team.
        team = removeSecurityProxy(self.factory.makeTeam())
        eric, rev1 = self.makePersonAndLinkedRevision()
        team.addMember(eric, team.teamowner)
        # Now make another revision by someone else in the team.
        bob, rev2 = self.makePersonAndLinkedRevision()
        team.addMember(bob, team.teamowner)
        # Other revisions have other authors.
        self.makeCachedRevision()
        revision_cache = getUtility(IRevisionCache).authoredBy(team)
        self.assertCollectionContents([rev1, rev2], revision_cache)

    def test_author_count(self):
        # The author count should count distinct revision authors.  Revision
        # authors linked to launchpad people use the person id as the
        # discriminator.

        # Make two revisions not assigned to anyone, then two revisions with
        # different revision names linked to the same person.
        revisions = [
            self.makeCachedRevision(revision=self.factory.makeRevision())
            for i in range(4)]
        # Make revisions [2] and [3] linked to the same person.
        person = self.factory.makePerson()
        removeSecurityProxy(revisions[2].revision_author).person = person
        removeSecurityProxy(revisions[3].revision_author).person = person
        revision_cache = getUtility(IRevisionCache)
        self.assertEqual(3, revision_cache.authorCount())

    def test_author_count_distinct(self):
        # If there are multiple revisions with the same revision author text,
        # but not linked to a Launchpad person, then that revision_text is
        # counted as one author.
        for counter in xrange(4):
            self.makeCachedRevision(revision=self.factory.makeRevision(
                author="Foo <foo@example.com>"))
        revision_cache = getUtility(IRevisionCache)
        self.assertEqual(1, revision_cache.authorCount())
