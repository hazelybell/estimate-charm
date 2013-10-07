# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lazr.restfulclient.errors import BadRequest
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.registry.enums import DistroSeriesDifferenceStatus
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifferenceSource,
    )
from lp.services.webapp.publisher import canonical_url
from lp.soyuz.enums import PackageDiffStatus
from lp.testing import (
    TestCaseWithFactory,
    ws_object,
    )
from lp.testing.layers import AppServerLayer


class DistroSeriesDifferenceWebServiceTestCase(TestCaseWithFactory):

    layer = AppServerLayer

    def test_get_difference(self):
        # DistroSeriesDifferences are available on the web service.
        ds_diff = self.factory.makeDistroSeriesDifference()
        ds_diff_path = canonical_url(ds_diff).replace(
            'http://launchpad.dev', '')

        ws_diff = ws_object(self.factory.makeLaunchpadService(), ds_diff)

        self.assertTrue(
            ws_diff.self_link.endswith(ds_diff_path))

    def test_blacklist(self):
        # The blacklist method can be called by people with admin access.
        ds_diff = self.factory.makeDistroSeriesDifference()
        archive_admin = self.factory.makeArchiveAdmin(
            archive=ds_diff.derived_series.main_archive)
        ws_diff = ws_object(self.factory.makeLaunchpadService(
            archive_admin), ds_diff)

        ws_diff.blacklist()
        transaction.commit()

        utility = getUtility(IDistroSeriesDifferenceSource)
        ds_diff = utility.getByDistroSeriesNameAndParentSeries(
            ds_diff.derived_series, ds_diff.source_package_name.name,
            ds_diff.parent_series)
        self.assertEqual(
            DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT,
            ds_diff.status)

    def test_unblacklist(self):
        # The unblacklist method can be called by people with admin access.
        ds_diff = self.factory.makeDistroSeriesDifference(
            status=DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT)
        archive_admin = self.factory.makeArchiveAdmin(
            archive=ds_diff.derived_series.main_archive)
        ws_diff = ws_object(self.factory.makeLaunchpadService(
            archive_admin), ds_diff)

        ws_diff.unblacklist()
        transaction.commit()

        utility = getUtility(IDistroSeriesDifferenceSource)
        ds_diff = utility.getByDistroSeriesNameAndParentSeries(
            ds_diff.derived_series, ds_diff.source_package_name.name,
            ds_diff.parent_series)
        self.assertEqual(
            DistroSeriesDifferenceStatus.NEEDS_ATTENTION,
            ds_diff.status)

    def test_addComment(self):
        # Comments can be added via the API
        ds_diff = self.factory.makeDistroSeriesDifference()
        ws_diff = ws_object(self.factory.makeLaunchpadService(
            self.factory.makePerson()), ds_diff)

        result = ws_diff.addComment(comment='Hey there')

        self.assertEqual('Hey there', result['body_text'])
        self.assertTrue(
            result['resource_type_link'].endswith(
                '#distro_series_difference_comment'))

    def test_requestDiffs(self):
        # The generation of package diffs can be requested via the API.
        derived_changelog = self.factory.makeChangelog(
            versions=['1.0', '1.2'])
        parent_changelog = self.factory.makeChangelog(
            versions=['1.0', '1.3'])
        transaction.commit()  # Yay, librarian.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str='foo', versions={
                'derived': '1.2',
                'parent': '1.3',
                'base': '1.0'},
            changelogs={
                'derived': derived_changelog,
                'parent': parent_changelog,
                })
        ws_diff = ws_object(self.factory.makeLaunchpadService(
            self.factory.makePerson()), ds_diff)

        ws_diff.requestPackageDiffs()
        transaction.commit()

        # Reload and check that the package diffs are there.
        utility = getUtility(IDistroSeriesDifferenceSource)
        ds_diff = utility.getByDistroSeriesNameAndParentSeries(
            ds_diff.derived_series, ds_diff.source_package_name.name,
            ds_diff.parent_series)
        self.assertIsNot(None, ds_diff.package_diff)
        self.assertIsNot(None, ds_diff.parent_package_diff)

    def test_requestPackageDiffs_exception(self):
        # If one of the pubs is missing an exception is raised.
        ds_diff = self.factory.makeDistroSeriesDifference(versions={
            'derived': '1.2',
            'parent': '1.3',
            })

        ws_diff = ws_object(self.factory.makeLaunchpadService(
            self.factory.makePerson()), ds_diff)

        self.assertRaises(
            BadRequest, ws_diff.requestPackageDiffs)

    def _createWSForDSDWithRequestedPackageDiff(self, versions):
        # Helper to create and return a webservice for a
        # DistroSeriesDifference with requested package diff(s).
        ds_diff = self.factory.makeDistroSeriesDifference(versions=versions,
            set_base_version=True)
        ws_diff = ws_object(self.factory.makeLaunchpadService(
            self.factory.makePerson()), ds_diff)
        ws_diff.requestPackageDiffs()
        transaction.commit()
        return ws_diff

    def test_requestPackageDiffs_exception_already_requested_derived(self):
        # When a package diff between the derived version and the base version
        # has already been requested, a call to request it again triggers a
        # BadRequest exception.
        ws_diff = self._createWSForDSDWithRequestedPackageDiff(versions={
            'derived': '1.2',
            'base': '1.2'})
        self.assertRaises(BadRequest, ws_diff.requestPackageDiffs)

    def test_requestPackageDiffs_exception_already_requested_parent(self):
        # When a package diff between the parent version and the base version
        # has already been requested, a call to request it again triggers a
        # BadRequest exception.
        ws_diff = self._createWSForDSDWithRequestedPackageDiff(versions={
            'parent': '1.3',
            'base': '1.2'})
        self.assertRaises(BadRequest, ws_diff.requestPackageDiffs)

    def test_package_diffs(self):
        # The package diff urls exposed.
        ds_diff = self.factory.makeDistroSeriesDifference()
        naked_dsdiff = removeSecurityProxy(ds_diff)
        naked_dsdiff.package_diff = self.factory.makePackageDiff(
            status=PackageDiffStatus.PENDING)
        naked_dsdiff.parent_package_diff = self.factory.makePackageDiff()

        ws_diff = ws_object(self.factory.makeLaunchpadService(
            self.factory.makePerson()), ds_diff)

        self.assertIs(None, ws_diff.package_diff_url)
        self.assertIsNot(None, ws_diff.parent_package_diff_url)

    def test_exported_status(self):
        # The difference's status is exposed.
        ds_diff = self.factory.makeDistroSeriesDifference(
            status=DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS)
        ws_diff = ws_object(self.factory.makeLaunchpadService(
            self.factory.makePerson()), ds_diff)

        self.assertEqual(u'Blacklisted always', ws_diff.status)

    def test_exported_sourcepackagename(self):
        # The difference's sourcepackagename is exposed.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str=u'package')
        ws_diff = ws_object(self.factory.makeLaunchpadService(
            self.factory.makePerson()), ds_diff)

        self.assertEqual(u'package', ws_diff.sourcepackagename)

    def test_exported_parent_source_version(self):
        # The difference's parent_source_version is exposed.
        ds_diff = self.factory.makeDistroSeriesDifference(
            versions={'parent': u'1.1'})
        ws_diff = ws_object(self.factory.makeLaunchpadService(
            self.factory.makePerson()), ds_diff)

        self.assertEqual(u'1.1', ws_diff.parent_source_version)

    def test_exported_source_version(self):
        # The difference's source_version is exposed.
        ds_diff = self.factory.makeDistroSeriesDifference(
            versions={'derived': u'1.3'})
        ws_diff = ws_object(self.factory.makeLaunchpadService(
            self.factory.makePerson()), ds_diff)

        self.assertEqual(u'1.3', ws_diff.source_version)

    def test_exported_base_version(self):
        # The difference's base_version is exposed.
        ds_diff = self.factory.makeDistroSeriesDifference(
            versions={'base': u'0.5'}, set_base_version=True)
        ws_diff = ws_object(self.factory.makeLaunchpadService(
            self.factory.makePerson()), ds_diff)

        self.assertEqual(u'0.5', ws_diff.base_version)
