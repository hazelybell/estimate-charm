# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test BinaryPackageName."""

__metaclass__ = type

from datetime import datetime

import pytz
from zope.component import getUtility

from lp.app.errors import NotFoundError
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.interfaces.binarypackagename import IBinaryPackageNameSet
from lp.soyuz.model.binarypackagename import getBinaryPackageDescriptions
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestBinaryPackageNameSet(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBinaryPackageNameSet, self).setUp()
        self.name_set = getUtility(IBinaryPackageNameSet)

    def test___getitem__found(self):
        name = self.factory.makeBinaryPackageName()
        self.assertEqual(name, self.name_set[name.name])

    def test___getitem__not_found(self):
        self.assertRaises(
            NotFoundError, lambda name: self.name_set[name], "notfound")

    def test_getAll_contains_one(self):
        name = self.factory.makeBinaryPackageName()
        self.assertIn(name, self.name_set.getAll())

    def test_queryByName_not_found(self):
        self.assertEqual(None, self.name_set.queryByName("notfound"))

    def test_queryByName_found(self):
        name = self.factory.makeBinaryPackageName()
        self.assertEqual(name, self.name_set.queryByName(name.name))

    def test_new(self):
        name = self.name_set.new("apackage")
        self.assertEqual("apackage", name.name)

    def test_getOrCreateByName_get(self):
        name = self.factory.makeBinaryPackageName()
        self.assertEqual(name, self.name_set.getOrCreateByName(name.name))

    def test_getOrCreateByName_create(self):
        self.assertEqual(
            "apackage", self.name_set.getOrCreateByName("apackage").name)

    def test_ensure_get(self):
        name = self.factory.makeBinaryPackageName()
        self.assertEqual(name, self.name_set.ensure(name.name))

    def test_ensure_create(self):
        self.assertEqual(
            "apackage", self.name_set.ensure("apackage").name)

    def createPublishingRecords(self, status=None):
        distroseries = self.factory.makeDistroSeries()
        distroarchseries = self.factory.makeDistroArchSeries(
            distroseries=distroseries)
        archives = [
            self.factory.makeArchive(distribution=distroseries.distribution),
            self.factory.makeArchive(distribution=distroseries.distribution),
            ]
        names = [
            self.factory.makeBinaryPackageName(),
            self.factory.makeBinaryPackageName(),
            self.factory.makeBinaryPackageName(),
            ]
        for i in range(2):
            bpr = self.factory.makeBinaryPackageRelease(
                binarypackagename=names[i])
            self.factory.makeBinaryPackagePublishingHistory(
                binarypackagerelease=bpr,
                status=PackagePublishingStatus.PUBLISHED,
                archive=archives[i],
                distroarchseries=distroarchseries,
                )
        return names, distroarchseries, archives

    def test_getNotNewByNames_excludes_unpublished(self):
        names, distroarchseries, archives = self.createPublishingRecords()
        self.assertEqual(
            sorted([names[0], names[1]]),
            sorted(self.name_set.getNotNewByNames(
                [name.id for name in names], distroarchseries.distroseries,
                [archive.id for archive in archives])))

    def test_getNotNewByNames_excludes_by_status(self):
        names, distroarchseries, archives = self.createPublishingRecords()
        bpr = self.factory.makeBinaryPackageRelease(
            binarypackagename=names[2])
        self.factory.makeBinaryPackagePublishingHistory(
            binarypackagerelease=bpr,
            status=PackagePublishingStatus.DELETED,
            archive=archives[0], distroarchseries=distroarchseries)
        self.assertEqual(
            sorted([names[0], names[1]]),
            sorted(self.name_set.getNotNewByNames(
                [name.id for name in names], distroarchseries.distroseries,
                [archive.id for archive in archives])))

    def test_getNotNewByNames_excludes_by_name_id(self):
        names, distroarchseries, archives = self.createPublishingRecords()
        self.assertEqual(
            [names[1]],
            list(self.name_set.getNotNewByNames(
                [name.id for name in names[1:]],
                distroarchseries.distroseries,
                [archive.id for archive in archives])))

    def test_getNotNewByNames_excludes_by_distroseries(self):
        names, distroarchseries, archives = self.createPublishingRecords()
        bpr = self.factory.makeBinaryPackageRelease(
            binarypackagename=names[2])
        self.factory.makeBinaryPackagePublishingHistory(
            binarypackagerelease=bpr,
            status=PackagePublishingStatus.PUBLISHED,
            archive=archives[0])
        self.assertEqual(
            sorted([names[0], names[1]]),
            sorted(self.name_set.getNotNewByNames(
                [name.id for name in names], distroarchseries.distroseries,
                [archive.id for archive in archives])))

    def test_getNotNewByNames_excludes_by_archive(self):
        names, distroarchseries, archives = self.createPublishingRecords()
        self.assertEqual(
            [names[0]],
            list(self.name_set.getNotNewByNames(
                [name.id for name in names], distroarchseries.distroseries,
                [archive.id for archive in archives[:1]])))

    def test_getBinaryPackageDescriptions_none(self):
        self.assertEqual({}, getBinaryPackageDescriptions([]))

    def test_getBinaryPackageDescriptions_no_release(self):
        name = self.factory.makeBinaryPackageName()
        self.assertEqual({}, getBinaryPackageDescriptions([name]))

    def test_getBinaryPackageDescriptions_one_release(self):
        name = self.factory.makeBinaryPackageName()
        self.factory.makeBinaryPackageRelease(
            binarypackagename=name, description="foo")
        self.assertEqual(
            {name.name: "foo"},
            getBinaryPackageDescriptions([name], max_title_length=3))

    def test_getBinaryPackageDescriptions_shortens_names(self):
        name = self.factory.makeBinaryPackageName()
        self.factory.makeBinaryPackageRelease(
            binarypackagename=name, description="foot")
        self.assertEqual(
            {name.name: "foo..."},
            getBinaryPackageDescriptions([name], max_title_length=3))

    def test_getBinaryPackageDescriptions_uses_latest(self):
        name = self.factory.makeBinaryPackageName()
        self.factory.makeBinaryPackageRelease(
            binarypackagename=name, description="foo",
            date_created=datetime(1980, 01, 01, tzinfo=pytz.UTC))
        self.factory.makeBinaryPackageRelease(
            binarypackagename=name, description="bar",
            date_created=datetime(2000, 01, 01, tzinfo=pytz.UTC))
        self.assertEqual(
            {name.name: "bar"},
            getBinaryPackageDescriptions([name], max_title_length=3))

    def test_getBinaryPackageDescriptions_two_packages(self):
        name1 = self.factory.makeBinaryPackageName()
        name2 = self.factory.makeBinaryPackageName()
        self.factory.makeBinaryPackageRelease(
            binarypackagename=name1, description="foo")
        self.factory.makeBinaryPackageRelease(
            binarypackagename=name2, description="bar")
        self.assertEqual(
            {name1.name: "foo", name2.name: "bar"},
            getBinaryPackageDescriptions([name1, name2], max_title_length=3))

    def test_getBinaryPackageDescriptions_strips_newlines(self):
        name = self.factory.makeBinaryPackageName()
        self.factory.makeBinaryPackageRelease(
            binarypackagename=name, description="f\no")
        self.assertEqual(
            {name.name: "f o"},
            getBinaryPackageDescriptions([name], max_title_length=3))

    def test_getBinaryPackageDescriptions_use_names(self):
        name = self.factory.makeBinaryPackageName()
        self.factory.makeBinaryPackageRelease(
            binarypackagename=name, description="foo")
        self.assertEqual(
            {name.name: "foo"},
            getBinaryPackageDescriptions(
                [name], use_names=True, max_title_length=3))
