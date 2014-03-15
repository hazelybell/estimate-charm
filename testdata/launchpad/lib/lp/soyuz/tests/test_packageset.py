# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test Packageset features."""

from zope.component import getUtility
from zope.security.interfaces import Unauthorized

from lp.app.errors import NotFoundError
from lp.registry.errors import NoSuchSourcePackageName
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.series import SeriesStatus
from lp.services.database.interfaces import IStore
from lp.soyuz.enums import ArchivePermissionType
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet
from lp.soyuz.interfaces.packageset import (
    DuplicatePackagesetName,
    IPackagesetSet,
    NoSuchPackageSet,
    )
from lp.soyuz.model.packagesetgroup import PackagesetGroup
from lp.testing import (
    admin_logged_in,
    celebrity_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    ZopelessDatabaseLayer,
    )


class TestPackagesetSet(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestPackagesetSet, self).setUp()
        self.ps_set = getUtility(IPackagesetSet)

    def getUbuntu(self):
        """Get the Ubuntu `Distribution`."""
        return getUtility(IDistributionSet).getByName('ubuntu')

    def makeExperimentalSeries(self):
        """Create an experimental Ubuntu `DistroSeries`."""
        return self.factory.makeDistroSeries(
            distribution=self.getUbuntu(), name="experimental",
            status=SeriesStatus.EXPERIMENTAL)

    def test_new_defaults_to_current_distroseries(self):
        # If the distroseries is not provided, the current development
        # distroseries will be assumed.
        packageset = self.ps_set.new(
            self.factory.getUniqueUnicode(), self.factory.getUniqueUnicode(),
            self.factory.makePerson())
        self.failUnlessEqual(
            self.getUbuntu().currentseries, packageset.distroseries)

    def test_new_with_specified_distroseries(self):
        # A distroseries can be provided when creating a package set.
        experimental_series = self.makeExperimentalSeries()
        packageset = self.ps_set.new(
            self.factory.getUniqueUnicode(), self.factory.getUniqueUnicode(),
            self.factory.makePerson(), distroseries=experimental_series)
        self.failUnlessEqual(experimental_series, packageset.distroseries)

    def test_new_creates_new_packageset_group(self):
        # Creating a new packageset should also create a new packageset
        # group with the same owner.
        owner = self.factory.makePerson()
        experimental_series = self.makeExperimentalSeries()
        packageset = self.ps_set.new(
            self.factory.getUniqueUnicode(), self.factory.getUniqueUnicode(),
            owner, distroseries=experimental_series)
        self.failUnlessEqual(owner, packageset.packagesetgroup.owner)

    def test_new_duplicate_name_for_same_distroseries(self):
        # Creating a packageset with a duplicate name for the
        # given distroseries will fail.
        distroseries = self.factory.makeDistroSeries()
        name = self.factory.getUniqueUnicode()
        self.factory.makePackageset(name, distroseries=distroseries)
        self.assertRaises(
            DuplicatePackagesetName, self.ps_set.new,
            name, self.factory.getUniqueUnicode(), self.factory.makePerson(),
            distroseries=distroseries)

    def test_new_duplicate_name_for_different_distroseries(self):
        # Creating a packageset with a duplicate name but for a different
        # series is no problem.
        name = self.factory.getUniqueUnicode()
        packageset1 = self.factory.makePackageset(name)
        packageset2 = self.ps_set.new(
            name, self.factory.getUniqueUnicode(), self.factory.makePerson(),
            distroseries=self.factory.makeDistroSeries())
        self.assertEqual(packageset1.name, packageset2.name)

    def test_new_related_packageset(self):
        # Creating a new package set while specifying a `related_set` should
        # have the effect that the former ends up in the same group as the
        # latter.
        name = self.factory.getUniqueUnicode()
        pset1 = self.factory.makePackageset(name)
        pset2 = self.factory.makePackageset(
            name, distroseries=self.makeExperimentalSeries(),
            related_set=pset1)
        self.assertEqual(pset1.packagesetgroup, pset2.packagesetgroup)

    def test_get_by_name_in_current_distroseries(self):
        # IPackagesetSet.getByName() will return the package set in the
        # current distroseries if the optional `distroseries` parameter is
        # omitted.
        name = self.factory.getUniqueUnicode()
        pset1 = self.factory.makePackageset(name)
        self.factory.makePackageset(
            name, distroseries=self.makeExperimentalSeries(),
            related_set=pset1)
        self.assertEqual(pset1, self.ps_set.getByName(name))

    def test_get_by_name_in_specified_distroseries(self):
        # IPackagesetSet.getByName() will return the package set in the
        # specified distroseries.
        name = self.factory.getUniqueUnicode()
        experimental_series = self.makeExperimentalSeries()
        pset1 = self.factory.makePackageset(name)
        pset2 = self.factory.makePackageset(
            name, distroseries=experimental_series, related_set=pset1)
        pset_found = self.ps_set.getByName(
            name, distroseries=experimental_series)
        self.assertEqual(pset2, pset_found)

    def test_get_by_distroseries(self):
        # IPackagesetSet.getBySeries() will return those package sets
        # associated with the given distroseries.
        package_sets_for_current_ubuntu = [
            self.factory.makePackageset() for counter in xrange(2)]
        self.factory.makePackageset(
            distroseries=self.makeExperimentalSeries())
        self.assertContentEqual(
            package_sets_for_current_ubuntu,
            self.ps_set.getBySeries(self.getUbuntu().currentseries))

    def test_getForPackages_returns_packagesets(self):
        # getForPackages finds package sets for given source package
        # names in a distroseries, and maps them by
        # SourcePackageName.id.
        series = self.factory.makeDistroSeries()
        packageset = self.factory.makePackageset(distroseries=series)
        package = self.factory.makeSourcePackageName()
        packageset.addSources([package.name])
        self.assertEqual(
            {package.id: [packageset]},
            self.ps_set.getForPackages(series, [package.id]))

    def test_getForPackages_filters_by_distroseries(self):
        # getForPackages does not return packagesets for different
        # distroseries.
        series = self.factory.makeDistroSeries()
        other_series = self.factory.makeDistroSeries()
        packageset = self.factory.makePackageset(distroseries=series)
        package = self.factory.makeSourcePackageName()
        packageset.addSources([package.name])
        self.assertEqual(
            {}, self.ps_set.getForPackages(other_series, [package.id]))

    def test_getForPackages_filters_by_sourcepackagename(self):
        # getForPackages does not return packagesets for different
        # source package names.
        series = self.factory.makeDistroSeries()
        packageset = self.factory.makePackageset(distroseries=series)
        package = self.factory.makeSourcePackageName()
        other_package = self.factory.makeSourcePackageName()
        packageset.addSources([package.name])
        self.assertEqual(
            {}, self.ps_set.getForPackages(series, [other_package.id]))

    def test_getByOwner(self):
        # Sets can be looked up by owner
        person = self.factory.makePerson()
        self.factory.makePackageset(owner=person)
        self.assertEqual(self.ps_set.getByOwner(person).count(), 1)

    def test_dict_access(self):
        # The packagesetset acts as a dictionary
        packageset = self.factory.makePackageset()
        self.assertEqual(self.ps_set[packageset.name], packageset)

    def test_list(self):
        # get returns the first N (N=50 by default) package sets sorted by name
        # for iterating packagesets over the web services API
        psets = [self.factory.makePackageset() for i in range(5)]
        psets.sort(key=lambda p: p.name)

        self.assertEqual(list(self.ps_set.get()), psets)

    def buildSimpleHierarchy(self, series=None):
        parent = self.factory.makePackageset(distroseries=series)
        child = self.factory.makePackageset(distroseries=series)
        package = self.factory.makeSourcePackageName()
        parent.add((child,))
        child.add((package,))
        return parent, child, package

    def test_sets_including_source(self):
        # Returns the list of sets including a source package
        parent, child, package = self.buildSimpleHierarchy()
        self.assertEqual(
            sorted(self.ps_set.setsIncludingSource(package)),
            sorted((parent, child)))

        # And can be limited to direct inclusion
        result = self.ps_set.setsIncludingSource(
            package, direct_inclusion=True)
        self.assertEqual(list(result), [child])

    def test_sets_including_source_same_series(self):
        # setsIncludingSource by default searches the current series, but a
        # series can be specified
        series = self.factory.makeDistroSeries()
        parent, child, package = self.buildSimpleHierarchy(series)
        result = self.ps_set.setsIncludingSource(
            package, distroseries=series)
        self.assertEqual(sorted(result), sorted([parent, child]))

    def test_sets_including_source_different_series(self):
        # searches are limited to one series
        parent, child, package = self.buildSimpleHierarchy()
        series = self.factory.makeDistroSeries()
        result = self.ps_set.setsIncludingSource(
            package, distroseries=series)
        self.assertTrue(result.is_empty())

    def test_sets_including_source_by_name(self):
        # Returns the list osf sets including a source package
        parent, child, package = self.buildSimpleHierarchy()
        self.assertEqual(
            sorted(self.ps_set.setsIncludingSource(package.name)),
            sorted([parent, child]))

    def test_sets_including_source_unknown_name(self):
        # A non-existent package name will throw an exception
        self.assertRaises(
            NoSuchSourcePackageName,
            self.ps_set.setsIncludingSource, 'this-will-fail')


class TestPackagesetSetPermissions(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPackagesetSetPermissions, self).setUp()
        self.ps_set = getUtility(IPackagesetSet)

    def test_create_packageset_as_user(self):
        # Normal users can't create packagesets
        with person_logged_in(self.factory.makePerson()):
            self.assertRaises(Unauthorized, getattr, self.ps_set, 'new')

    def test_create_packagset_as_techboard(self):
        # Ubuntu techboard members can create packagesets
        with celebrity_logged_in('ubuntu_techboard'):
            self.ps_set.new(
                self.factory.getUniqueUnicode(),
                self.factory.getUniqueUnicode(),
                self.factory.makePerson())

    def test_create_packagset_as_admin(self):
        # Admins can create packagesets
        with admin_logged_in():
            self.ps_set.new(
                self.factory.getUniqueUnicode(),
                self.factory.getUniqueUnicode(),
                self.factory.makePerson())


class TestPackageset(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def setUp(self):
        """Setup a distribution with multiple distroseries."""
        super(TestPackageset, self).setUp()
        self.distribution = getUtility(IDistributionSet).getByName(
            'ubuntu')
        self.distroseries_current = self.distribution.currentseries
        self.distroseries_experimental = self.factory.makeDistroSeries(
            distribution=self.distribution, name="experimental",
            status=SeriesStatus.EXPERIMENTAL)
        self.distroseries_experimental2 = self.factory.makeDistroSeries(
            distribution=self.distribution, name="experimental2",
            status=SeriesStatus.EXPERIMENTAL)

        self.person1 = self.factory.makePerson(
            name='hacker', displayname=u'Happy Hacker')

        self.packageset_set = getUtility(IPackagesetSet)

    def test_no_related_sets(self):
        # If the package set is the only one in the group the result set
        # returned by relatedSets() is empty.
        packageset = self.packageset_set.new(
            u'kernel', u'Contains all OS kernel packages', self.person1)

        self.failUnlessEqual(packageset.relatedSets().count(), 0)

    def test_related_set_found(self):
        # Creating a new package set while specifying a `related_set` should
        # have the effect that the former ends up in the same group as the
        # latter.

        # The original package set.
        pset1 = self.packageset_set.new(
            u'kernel', u'Contains all OS kernel packages', self.person1)

        # A related package set.
        pset2 = self.packageset_set.new(
            u'kernel', u'A related package set.', self.person1,
            distroseries=self.distroseries_experimental, related_set=pset1)
        self.assertEqual(pset1.packagesetgroup, pset2.packagesetgroup)

        # An unrelated package set with the same name.
        pset3 = self.packageset_set.new(
            u'kernel', u'Unrelated package set.', self.person1,
            distroseries=self.distroseries_experimental2)
        self.assertNotEqual(pset2.packagesetgroup, pset3.packagesetgroup)

        # Make sure 'pset2' is related to 'pset1'.
        related = pset1.relatedSets()
        self.assertEqual(related.count(), 1)
        self.assertEqual(related[0], pset2)

        # And the other way around ..
        related = pset2.relatedSets()
        self.assertEqual(related.count(), 1)
        self.assertEqual(related[0], pset1)

        # Unsurprisingly, the unrelated package set is not associated with any
        # other package set.
        self.failUnlessEqual(pset3.relatedSets().count(), 0)

    def test_destroy(self):
        pset = self.packageset_set.new(
            u'kernel', u'Contains all OS kernel packages', self.person1)
        pset.destroySelf()
        self.assertRaises(NoSuchPackageSet, self.packageset_set.getByName,
                          u'kernel')

        # Did we clean up the single packagesetgroup?
        store = IStore(PackagesetGroup)
        result_set = store.find(PackagesetGroup)
        self.assertTrue(result_set.is_empty())

    def test_destroy_with_ancestor(self):
        ancestor = self.packageset_set.new(
            u'kernel', u'Contains all OS kernel packages', self.person1)
        pset = self.packageset_set.new(
            u'kernel', u'Contains all OS kernel packages', self.person1,
            distroseries=self.distroseries_experimental, related_set=ancestor)
        pset.destroySelf()
        self.assertRaises(
            NoSuchPackageSet, self.packageset_set.getByName,
            u'kernel', distroseries=self.distroseries_experimental)

    def test_destroy_with_packages(self):
        pset = self.packageset_set.new(
            u'kernel', u'Contains all OS kernel packages', self.person1)
        package = self.factory.makeSourcePackageName()
        pset.addSources([package.name])

        pset.destroySelf()
        self.assertRaises(NoSuchPackageSet, self.packageset_set.getByName,
                          u'kernel')

    def test_destroy_child(self):
        parent = self.packageset_set.new(
            u'core', u'Contains all the important packages', self.person1)
        child = self.packageset_set.new(
            u'kernel', u'Contains all OS kernel packages', self.person1)
        parent.add((child,))

        child.destroySelf()
        self.assertRaises(NoSuchPackageSet, self.packageset_set.getByName,
                          u'kernel')
        self.assertTrue(parent.setsIncluded(direct_inclusion=True).is_empty())

    def test_destroy_parent(self):
        parent = self.packageset_set.new(
            u'core', u'Contains all the important packages', self.person1)
        child = self.packageset_set.new(
            u'kernel', u'Contains all OS kernel packages', self.person1)
        parent.add((child,))

        parent.destroySelf()
        self.assertRaises(NoSuchPackageSet, self.packageset_set.getByName,
                          u'core')
        self.assertTrue(child.setsIncludedBy(direct_inclusion=True).is_empty())

    def test_destroy_intermidate(self):
        # Destroying an intermediate packageset severs the indirect inclusion
        parent = self.factory.makePackageset()
        child = self.factory.makePackageset()
        grandchild = self.factory.makePackageset()
        parent.add((child,))
        child.add((grandchild,))
        self.assertEqual(parent.setsIncluded().count(), 2)

        child.destroySelf()
        self.assertRaises(NoSuchPackageSet, self.packageset_set.getByName,
                          child.name)
        self.assertTrue(parent.setsIncluded().is_empty())

    def buildSet(self, size=5):
        packageset = self.factory.makePackageset()
        packages = [self.factory.makeSourcePackageName() for i in range(size)]
        packageset.add(packages)
        return packageset, packages

    def test_sources_included(self):
        # Lists the source packages included in a set
        packageset, packages = self.buildSet()
        self.assertEqual(
            sorted(packageset.sourcesIncluded()), sorted(packages))

    def test_get_sources_included(self):
        # Lists the names of source packages included in a set
        packageset, packages = self.buildSet()
        self.assertEqual(
            sorted(packageset.getSourcesIncluded()),
            sorted(p.name for p in packages))

    def test_sources_included_indirect(self):
        # sourcesIncluded traverses the set tree, by default
        packageset1, packages1 = self.buildSet()
        packageset2, packages2 = self.buildSet()
        packageset1.add((packageset2,))
        self.assertEqual(
            sorted(packageset1.sourcesIncluded()),
            sorted(packages1 + packages2))

        # direct_inclusion disables traversal
        self.assertEqual(
            sorted(packageset1.sourcesIncluded(direct_inclusion=True)),
            sorted(packages1))

    def test_sources_multiply_included(self):
        # Source packages included in multiple packagesets in a tree are only
        # listed once.
        packageset1, packages1 = self.buildSet(5)
        packageset2, packages2 = self.buildSet(5)
        packageset1.add(packages2[:2])
        packageset1.add((packageset2,))
        self.assertEqual(
            sorted(packageset1.sourcesIncluded(direct_inclusion=True)),
            sorted(packages1 + packages2[:2]))
        self.assertEqual(
            sorted(packageset1.sourcesIncluded()),
            sorted(packages1 + packages2))

    def test_add_already_included_sources(self):
        # Adding source packages to a package set repeatedly has no effect
        packageset, packages = self.buildSet()
        packageset.add(packages)
        self.assertEqual(
            sorted(packageset.sourcesIncluded()), sorted(packages))

    def test_remove_sources(self):
        # Source packages can be removed from a set
        packageset, packages = self.buildSet(5)
        packageset.remove(packages[:2])
        self.assertEqual(
            sorted(packageset.sourcesIncluded()), sorted(packages[2:]))

    def test_remove_non_preset_sources(self):
        # Trying to remove source packages that are *not* in the set, has no
        # effect.
        packageset, packages = self.buildSet()
        packageset.remove([self.factory.makeSourcePackageName()])
        self.assertTrue(sorted(packageset.sourcesIncluded()), sorted(packages))

    def test_sets_included(self):
        # Returns the sets included in a set
        parent = self.factory.makePackageset()
        child = self.factory.makePackageset()
        parent.add((child,))
        grandchild = self.factory.makePackageset()
        child.add((grandchild,))
        self.assertEqual(
            sorted(parent.setsIncluded()), sorted([child, grandchild]))
        self.assertEqual(
            list(parent.setsIncluded(direct_inclusion=True)), [child])

    def test_sets_included_multipath(self):
        # A set can be included by multiple paths, but will only appear once in
        # setsIncluded
        parent = self.factory.makePackageset()
        child = self.factory.makePackageset()
        child2 = self.factory.makePackageset()
        parent.add((child, child2))
        grandchild = self.factory.makePackageset()
        child.add((grandchild,))
        child2.add((grandchild,))
        self.assertEqual(
            sorted(parent.setsIncluded()), sorted([child, child2, grandchild]))

    def test_sets_included_by(self):
        # Returns the set of sets including a set
        parent = self.factory.makePackageset()
        child = self.factory.makePackageset()
        parent.add((child,))
        grandchild = self.factory.makePackageset()
        child.add((grandchild,))
        self.assertEqual(
            sorted(grandchild.setsIncludedBy()), sorted([child, parent]))
        self.assertEqual(
            list(grandchild.setsIncludedBy(direct_inclusion=True)), [child])

    def test_remove_subset(self):
        # A set can be removed from another set
        parent = self.factory.makePackageset()
        child = self.factory.makePackageset()
        child2 = self.factory.makePackageset()
        parent.add((child, child2))
        self.assertEqual(
            sorted(parent.setsIncluded()), sorted([child, child2]))
        parent.remove((child,))
        self.assertEqual(list(parent.setsIncluded()), [child2])

    def test_remove_indirect_subset(self):
        # Removing indirect successors has no effect.
        parent = self.factory.makePackageset()
        child = self.factory.makePackageset()
        grandchild = self.factory.makePackageset()
        parent.add((child,))
        child.add((grandchild,))
        self.assertEqual(
            sorted(parent.setsIncluded()), sorted([child, grandchild]))
        parent.remove((grandchild,))
        self.assertEqual(
            sorted(parent.setsIncluded()), sorted([child, grandchild]))

    def test_sources_shared_by(self):
        # Lists the source packages shared between two packagesets
        pset1, pkgs1 = self.buildSet(5)
        pset2, pkgs2 = self.buildSet(5)
        self.assertTrue(pset1.sourcesSharedBy(pset2).is_empty())

        pset1.add(pkgs2[:2])
        pset2.add(pkgs1[:2])
        self.assertEqual(
            sorted(pset1.sourcesSharedBy(pset2)),
            sorted(pkgs1[:2] + pkgs2[:2]))

    def test_get_sources_shared_by(self):
        # List the names of source packages shared between two packagesets
        pset1, pkgs1 = self.buildSet(5)
        pset2, pkgs2 = self.buildSet(5)
        self.assertEqual(pset1.getSourcesSharedBy(pset2), [])

        pset1.add(pkgs2[:2])
        pset2.add(pkgs1[:2])
        self.assertEqual(
            sorted(pset1.getSourcesSharedBy(pset2)),
            sorted(p.name for p in (pkgs1[:2] + pkgs2[:2])))

    def test_sources_shared_by_subset(self):
        # sourcesSharedBy takes subsets into account, unless told not to
        pset1, pkgs1 = self.buildSet()
        pset2, pkgs2 = self.buildSet()
        self.assertTrue(pset1.sourcesSharedBy(pset2).is_empty())

        pset1.add((pset2,))
        self.assertEqual(sorted(pset1.sourcesSharedBy(pset2)), sorted(pkgs2))
        self.assertTrue(
            pset1.sourcesSharedBy(pset2, direct_inclusion=True).is_empty())

    def test_sources_shared_by_symmetric(self):
        # sourcesSharedBy is symmetric
        pset1, pkgs1 = self.buildSet(5)
        pset2, pkgs2 = self.buildSet(5)
        pset3, pkgs3 = self.buildSet(5)
        self.assertTrue(pset1.sourcesSharedBy(pset2).is_empty())

        pset1.add(pkgs2[:2] + pkgs3)
        pset2.add(pkgs1[:2] + [pset3])
        self.assertEqual(
            sorted(pset1.sourcesSharedBy(pset2)),
            sorted(pkgs1[:2] + pkgs2[:2] + pkgs3))
        self.assertEqual(
            sorted(pset1.sourcesSharedBy(pset2)),
            sorted(pset2.sourcesSharedBy(pset1)))

    def test_sources_not_shared_by(self):
        # Lists source packages in the first set, but not the second
        pset1, pkgs1 = self.buildSet(5)
        pset2, pkgs2 = self.buildSet(5)
        self.assertEqual(
            sorted(pset1.sourcesNotSharedBy(pset2)), sorted(pkgs1))
        pset1.add(pkgs2[:2])
        pset2.add(pkgs1[:2])
        self.assertEqual(
            sorted(pset1.sourcesNotSharedBy(pset2)), sorted(pkgs1[2:]))

    def test_get_sources_not_shared_by(self):
        # List the names of source packages in the first set, but not the
        # second
        pset1, pkgs1 = self.buildSet(5)
        pset2, pkgs2 = self.buildSet(5)
        self.assertEqual(
            sorted(pset1.getSourcesNotSharedBy(pset2)),
            sorted(p.name for p in pkgs1))

        pset1.add(pkgs2[:2])
        pset2.add(pkgs1[:2])
        self.assertEqual(
            sorted(pset1.getSourcesNotSharedBy(pset2)),
            sorted(p.name for p in pkgs1[2:]))

    def test_sources_not_shared_by_subset(self):
        # sourcesNotSharedBy takes subsets into account, unless told not to
        pset1, pkgs1 = self.buildSet()
        pset2, pkgs2 = self.buildSet()
        self.assertTrue(sorted(pset1.sourcesNotSharedBy(pset2)), sorted(pkgs1))

        pset2.add((pset1,))
        self.assertTrue(pset1.sourcesNotSharedBy(pset2).is_empty())
        self.assertTrue(
            sorted(pset1.sourcesNotSharedBy(pset2, direct_inclusion=True)),
            sorted(pkgs1))

    def test_add_unknown_name(self):
        # Adding an unknown package name will raise an error
        pset = self.factory.makePackageset()
        self.assertRaises(
            AssertionError, pset.add, [self.factory.getUniqueUnicode()])

    def test_remove_unknown_name(self):
        # Removing an unknown package name will raise an error
        pset = self.factory.makePackageset()
        self.assertRaises(
            AssertionError, pset.remove, [self.factory.getUniqueUnicode()])

    def test_add_cycle(self):
        # Adding cycles to the graph will raise an error
        parent = self.factory.makePackageset()
        child = self.factory.makePackageset()
        parent.add((child,))
        self.assertRaises(Exception, child.add, (parent,))

    def test_add_indirect_cycle(self):
        # Adding indirect cycles to the graph will raise an error
        parent = self.factory.makePackageset()
        child = self.factory.makePackageset()
        grandchild = self.factory.makePackageset()
        parent.add((child,))
        child.add((grandchild,))
        self.assertRaises(Exception, grandchild.add, (parent,))


class TestPackagesetPermissions(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPackagesetPermissions, self).setUp()
        self.person = self.factory.makePerson()
        self.person2 = self.factory.makePerson()
        self.packageset = self.factory.makePackageset(owner=self.person)
        self.packageset2 = self.factory.makePackageset(owner=self.person)
        self.package = self.factory.makeSourcePackageName()

    def test_user_modify_packageset(self):
        # Normal users may not modify packagesets
        with person_logged_in(self.person2):
            self.assertRaises(
                Unauthorized, setattr, self.packageset, 'name', u'renamed')
            self.assertRaises(
                Unauthorized, setattr, self.packageset, 'description',
                u'Re-described')
            self.assertRaises(
                Unauthorized, setattr, self.packageset, 'owner', self.person2)
            self.assertRaises(
                Unauthorized, getattr, self.packageset, 'add')
            self.assertRaises(
                Unauthorized, getattr, self.packageset, 'remove')
            self.assertRaises(
                Unauthorized, getattr, self.packageset, 'addSources')
            self.assertRaises(
                Unauthorized, getattr, self.packageset, 'removeSources')
            self.assertRaises(
                Unauthorized, getattr, self.packageset, 'addSubsets')
            self.assertRaises(
                Unauthorized, getattr, self.packageset, 'removeSubsets')

    def modifyPackageset(self):
        self.packageset.name = u'renamed'
        self.packageset.description = u'Re-described'
        self.packageset.add((self.package,))
        self.packageset.remove((self.package,))
        self.packageset.addSources((self.package.name,))
        self.packageset.removeSources((self.package.name,))
        self.packageset.add((self.packageset2,))
        self.packageset.remove((self.packageset2,))
        self.packageset.addSubsets((self.packageset2.name,))
        self.packageset.removeSubsets((self.packageset2.name,))
        self.packageset.owner = self.person2

    def test_owner_modify_packageset(self):
        # Packageset owners can modify their packagesets
        with person_logged_in(self.person):
            self.modifyPackageset()

    def test_admin_modify_packageset(self):
        # Admins can modify packagesets
        with admin_logged_in():
            self.modifyPackageset()


class TestArchivePermissionSet(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestArchivePermissionSet, self).setUp()
        self.ap_set = getUtility(IArchivePermissionSet)
        self.archive = self.factory.makeArchive()
        self.packageset = self.factory.makePackageset()
        self.person = self.factory.makePerson()

    def test_packagesets_for_uploader_empty(self):
        # A new archive will have no upload permissions
        self.assertTrue(
            self.ap_set.packagesetsForUploader(
                self.archive, self.person).is_empty())

    def test_new_packageset_uploader_simple(self):
        # newPackagesetUploader grants upload rights to a packagset
        permission = self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)

        self.assertEqual(permission.archive, self.archive)
        self.assertEqual(permission.person, self.person)
        self.assertEqual(permission.packageset, self.packageset)
        self.assertEqual(permission.permission, ArchivePermissionType.UPLOAD)
        self.assertFalse(permission.explicit)
        # Convenience property:
        self.assertEqual(permission.package_set_name, self.packageset.name)

    def test_new_packageset_uploader_repeated(self):
        # Creating the same permission repeatedly should re-use the existing
        # permission.
        permission1 = self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        permission2 = self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        self.assertEqual(permission1.id, permission2.id)

    def test_new_packageset_uploader_repeated_explicit(self):
        # Attempting to create an explicit permission when a non-explicit one
        # exists already will fail.
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        self.assertRaises(ValueError, self.ap_set.newPackagesetUploader,
            self.archive, self.person, self.packageset, True)

    def test_new_packageset_uploader_repeated_implicit(self):
        # Attempting to create an implicit permission when an explicit one
        # exists already will fail.
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset, True)
        self.assertRaises(ValueError, self.ap_set.newPackagesetUploader,
            self.archive, self.person, self.packageset)

    def test_new_packageset_uploader_teammember(self):
        # If a team member already has upload rights through a team, they can
        # be granted again, individually
        team = self.factory.makeTeam(self.person)
        self.ap_set.newPackagesetUploader(
            self.archive, team, self.packageset)
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)

        # Unless the explicit flag conflicts
        self.assertRaises(ValueError, self.ap_set.newPackagesetUploader,
            self.archive, self.person, self.packageset, True)

    def test_packagesets_for_uploader(self):
        # packagesetsForUploader returns the packageset upload archive
        # permissions granted to a person
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)

        permission = self.ap_set.packagesetsForUploader(
            self.archive, self.person).one()
        self.assertEqual(permission.archive, self.archive)
        self.assertEqual(permission.person, self.person)
        self.assertEqual(permission.packageset, self.packageset)
        self.assertEqual(permission.permission, ArchivePermissionType.UPLOAD)
        self.assertFalse(permission.explicit)

    def test_packagesets_for_source_uploader(self):
        # packagesetsForSourceUploader returns the packageset upload archive
        # permissions granted to a person affecting a given package
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        package = self.factory.makeSourcePackageName()
        self.packageset.add((package,))

        permission = self.ap_set.packagesetsForSourceUploader(
            self.archive, package, self.person).one()
        self.assertEqual(permission.archive, self.archive)
        self.assertEqual(permission.person, self.person)
        self.assertEqual(permission.packageset, self.packageset)
        self.assertEqual(permission.permission, ArchivePermissionType.UPLOAD)
        self.assertFalse(permission.explicit)

    def test_packagesets_for_source_uploader_by_name(self):
        # packagesetsForSourceUploader can take a package name
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        package = self.factory.makeSourcePackageName()
        self.packageset.add((package,))

        self.assertFalse(self.ap_set.packagesetsForSourceUploader(
            self.archive, package.name, self.person).is_empty())

        # and will raise an exception if the name is invalid
        self.assertRaises(
            NoSuchSourcePackageName, self.ap_set.packagesetsForSourceUploader,
            self.archive, self.factory.getUniqueUnicode(), self.person)

    def test_packagesets_for_source(self):
        # packagesetsForSource returns the packageset upload archive
        # permissions affecting a given package
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        package = self.factory.makeSourcePackageName()
        self.packageset.add((package,))

        permission = self.ap_set.packagesetsForSource(
            self.archive, package).one()
        self.assertEqual(permission.archive, self.archive)
        self.assertEqual(permission.person, self.person)
        self.assertEqual(permission.packageset, self.packageset)
        self.assertEqual(permission.permission, ArchivePermissionType.UPLOAD)
        self.assertFalse(permission.explicit)

    def test_uploaders_for_packageset(self):
        # uploadersForPackageset returns the people with upload rigts for a
        # packageset in a given archive
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)

        permission = self.ap_set.uploadersForPackageset(
            self.archive, self.packageset).one()
        self.assertEqual(permission.archive, self.archive)
        self.assertEqual(permission.person, self.person)
        self.assertEqual(permission.packageset, self.packageset)
        self.assertEqual(permission.permission, ArchivePermissionType.UPLOAD)
        self.assertFalse(permission.explicit)

    def test_uploaders_for_packageset_subpackagesets(self):
        # archive permissions apply to children of a packageset, unless they
        # have their own permissions with the "explicit" flag set
        child = self.factory.makePackageset()
        self.packageset.add((child,))
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)

        # uploadersForPackageset will not list them:
        self.assertTrue(
            self.ap_set.uploadersForPackageset(self.archive, child).is_empty())

        # unless told to:
        self.assertFalse(
            self.ap_set.uploadersForPackageset(
                self.archive, child, direct_permissions=False).is_empty())

    def test_uploaders_for_packageset_explicit(self):
        # people can have both explicit and implicit upload rights to a
        # packageset
        child = self.factory.makePackageset()
        self.packageset.add((child,))
        implicit_parent = self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        explicit_child = self.ap_set.newPackagesetUploader(
            self.archive, self.person, child, True)

        self.assertEqual(
            sorted(self.ap_set.uploadersForPackageset(
                self.archive, child, direct_permissions=False)),
            sorted((implicit_parent, explicit_child)))

    def test_uploaders_for_packageset_subpackagesets_removed(self):
        # archive permissions cease to apply to removed child packagesets
        child = self.factory.makePackageset()
        self.packageset.add((child,))
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        self.assertFalse(
            self.ap_set.uploadersForPackageset(
                self.archive, child, direct_permissions=False).is_empty())

        self.packageset.remove((child,))
        self.assertTrue(
            self.ap_set.uploadersForPackageset(
                self.archive, child, direct_permissions=False).is_empty())

    def test_uploaders_for_packageset_by_name(self):
        # a packageset name that doesn't exist will throw an error
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        # A correct name will give us a result:
        self.assertFalse(self.ap_set.uploadersForPackageset(
            self.archive, self.packageset.name).is_empty())
        # An incorrect one will raise an exception
        self.assertRaises(
            NotFoundError, self.ap_set.uploadersForPackageset,
            self.archive, self.factory.getUniqueUnicode())
        # An incorrect type will raise a ValueError
        self.assertRaises(
            ValueError, self.ap_set.uploadersForPackageset,
            self.archive, 42)

    def test_archive_permission_per_archive(self):
        # archive permissions are limited to an archive
        archive2 = self.factory.makeArchive()
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        self.assertTrue(
            self.ap_set.packagesetsForUploader(
                archive2, self.person).is_empty())

    def test_check_authenticated_packageset(self):
        # checkAuthenticated is a generic way to look up archive permissions
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)

        permissions = self.ap_set.checkAuthenticated(
            self.person, self.archive, ArchivePermissionType.UPLOAD,
            self.packageset)

        self.assertEqual(permissions.count(), 1)
        permission = permissions[0]

        self.assertEqual(permission.archive, self.archive)
        self.assertEqual(permission.person, self.person)
        self.assertEqual(permission.packageset, self.packageset)
        self.assertEqual(permission.permission, ArchivePermissionType.UPLOAD)
        self.assertFalse(permission.explicit)

    def test_is_source_upload_allowed(self):
        # isSourceUploadAllowed indicates whether a user has any archive
        # permissinos granting them upload access to a specific source package
        # (excepting component permissions)
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        package = self.factory.makeSourcePackageName()
        self.packageset.add((package,))

        self.assertTrue(self.ap_set.isSourceUploadAllowed(
            self.archive, package, self.person))

    def test_is_source_upload_allowed_denied(self):
        # isSourceUploadAllowed should return false when a user has no
        # packageset/PPU permission granting upload rights
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        package = self.factory.makeSourcePackageName()

        self.assertFalse(self.ap_set.isSourceUploadAllowed(
            self.archive, package, self.person))

    def test_explicit_packageset_upload_rights(self):
        # If a package is covered by a packageset with explicit upload rights,
        # they disable all implicit upload rights to that package through other
        # packagesets.
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        package = self.factory.makeSourcePackageName()
        package2 = self.factory.makeSourcePackageName()
        self.packageset.add((package, package2))

        self.assertTrue(self.ap_set.isSourceUploadAllowed(
            self.archive, package, self.person))
        self.assertTrue(self.ap_set.isSourceUploadAllowed(
            self.archive, package2, self.person))

        # Create a packageset with explicit rights to package
        special_person = self.factory.makePerson()
        special_packageset = self.factory.makePackageset()
        special_packageset.add((package,))
        self.ap_set.newPackagesetUploader(
            self.archive, special_person, special_packageset, True)

        self.assertFalse(self.ap_set.isSourceUploadAllowed(
            self.archive, package, self.person))
        self.assertTrue(self.ap_set.isSourceUploadAllowed(
            self.archive, package2, self.person))
        self.assertTrue(self.ap_set.isSourceUploadAllowed(
            self.archive, package, special_person))
        self.assertFalse(self.ap_set.isSourceUploadAllowed(
            self.archive, package2, special_person))

    def test_delete_packageset_uploader(self):
        # deletePackagesetUploader removes upload rights
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)
        self.assertFalse(
            self.ap_set.packagesetsForUploader(
                self.archive, self.person).is_empty())

        self.ap_set.deletePackagesetUploader(
            self.archive, self.person, self.packageset)
        self.assertTrue(
            self.ap_set.packagesetsForUploader(
                self.archive, self.person).is_empty())

    def test_delete_packageset(self):
        # Packagesets can't be deleted as long as they have uploaders
        self.ap_set.newPackagesetUploader(
            self.archive, self.person, self.packageset)

        self.assertRaises(Exception, self.packageset.destroySelf)
