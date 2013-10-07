# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test ArchiveArch features."""

from zope.component import getUtility

from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import IPersonSet
from lp.soyuz.interfaces.archivearch import IArchiveArchSet
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer


class TestArchiveArch(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Use `SoyuzTestPublisher` to publish some sources in archives."""
        super(TestArchiveArch, self).setUp()

        self.archive_arch_set = getUtility(IArchiveArchSet)
        self.ppa = getUtility(IPersonSet).getByName('cprov').archive
        ubuntu = getUtility(IDistributionSet)['ubuntu']
        self.ubuntu_archive = ubuntu.main_archive
        self.cell_proc = self.factory.makeProcessor(
            'cell-proc', 'PS cell processor', 'Screamingly faaaaaaaaaaaast',
            True)
        self.omap = self.factory.makeProcessor(
            'omap', 'Multimedia applications processor',
            'Does all your sound & video', True)

    def test_getRestrictedProcessors_no_restricted_associations(self):
        # Our archive is not associated with any restricted processors yet.
        result_set = list(
            self.archive_arch_set.getRestrictedProcessors(self.ppa))
        archivearches = [row[1] for row in result_set]
        self.assertTrue(all(aa is None for aa in archivearches))

    def test_getRestrictedProcessors_single_restricted_association(self):
        # Our archive is now associated with one of the restricted processors.
        self.archive_arch_set.new(self.ppa, self.cell_proc)
        result_set = list(
            self.archive_arch_set.getRestrictedProcessors(self.ppa))
        results = dict(
            (row[0].name, row[1] is not None) for row in result_set)
        self.assertEqual({'cell-proc': True, 'omap': False}, results)

    def test_getRestrictedProcessors_archive_only(self):
        # Test that only the associated archs for the archive itself are
        # returned.
        self.archive_arch_set.new(self.ppa, self.cell_proc)
        self.archive_arch_set.new(self.ubuntu_archive, self.omap)
        result_set = list(
            self.archive_arch_set.getRestrictedProcessors(self.ppa))
        results = dict(
            (row[0].name, row[1] is not None) for row in result_set)
        self.assertEqual({'cell-proc': True, 'omap': False}, results)

    def test_getByArchive_no_other_archives(self):
        # Test ArchiveArchSet.getByArchive returns no other archives.
        self.archive_arch_set.new(self.ppa, self.cell_proc)
        self.archive_arch_set.new(self.ubuntu_archive, self.omap)
        result_set = list(self.archive_arch_set.getByArchive(self.ppa))
        self.assertEqual(1, len(result_set))
        self.assertEqual(self.ppa, result_set[0].archive)
        self.assertEqual(self.cell_proc, result_set[0].processor)

    def test_getByArchive_follows_creation_order(self):
        # The result of ArchiveArchSet.getByArchive follows the order in
        # which architecture associations were added.
        self.archive_arch_set.new(self.ppa, self.cell_proc)
        self.archive_arch_set.new(self.ppa, self.omap)
        result_set = list(self.archive_arch_set.getByArchive(self.ppa))
        self.assertEqual(2, len(result_set))
        self.assertEqual(self.ppa, result_set[0].archive)
        self.assertEqual(self.cell_proc, result_set[0].processor)
        self.assertEqual(self.ppa, result_set[1].archive)
        self.assertEqual(self.omap, result_set[1].processor)

    def test_getByArchive_specific_architecture(self):
        # ArchiveArchSet.getByArchive can query for a specific architecture
        # association.
        self.archive_arch_set.new(self.ppa, self.cell_proc)
        self.archive_arch_set.new(self.ppa, self.omap)
        result_set = list(
            self.archive_arch_set.getByArchive(self.ppa, self.cell_proc))
        self.assertEqual(1, len(result_set))
        self.assertEqual(self.ppa, result_set[0].archive)
        self.assertEqual(self.cell_proc, result_set[0].processor)
