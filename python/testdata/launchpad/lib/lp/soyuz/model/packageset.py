# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['Packageset', 'PackagesetSet']

import pytz
from storm.exceptions import IntegrityError
from storm.expr import SQL
from storm.locals import (
    DateTime,
    Int,
    Reference,
    Storm,
    Unicode,
    )
from zope.component import getUtility
from zope.interface import implements

from lp.app.errors import NotFoundError
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.sourcepackagename import (
    ISourcePackageName,
    ISourcePackageNameSet,
    )
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.helpers import ensure_unicode
from lp.soyuz.interfaces.packageset import (
    DuplicatePackagesetName,
    IPackageset,
    IPackagesetSet,
    NoSuchPackageSet,
    )
from lp.soyuz.model.packagesetgroup import PackagesetGroup
from lp.soyuz.model.packagesetsources import PackagesetSources


def _order_result_set(result_set):
    """Default order for package set and source package name result sets."""
    return result_set.order_by('name')


def _extract_type_name(value):
    """Extract the type name of the given value."""
    return str(type(value)).split("'")[-2]


class Packageset(Storm):
    """See `IPackageset`."""
    implements(IPackageset)
    __storm_table__ = 'Packageset'
    id = Int(primary=True)

    date_created = DateTime(
        name='date_created', allow_none=False, tzinfo=pytz.UTC)

    owner_id = Int(name='owner', allow_none=False)
    owner = Reference(owner_id, 'Person.id')

    name = Unicode(name='name', allow_none=False)
    description = Unicode(name='description', allow_none=False)

    distroseries_id = Int(name='distroseries', allow_none=False)
    distroseries = Reference(distroseries_id, 'DistroSeries.id')

    packagesetgroup_id = Int(name='packagesetgroup', allow_none=False)
    packagesetgroup = Reference(packagesetgroup_id, 'PackagesetGroup.id')

    relative_build_score = Int(allow_none=False)

    def add(self, data):
        """See `IPackageset`."""
        handlers = (
            (ISourcePackageName, self._addSourcePackageNames),
            (IPackageset, self._addDirectSuccessors))
        self._add_or_remove(data, handlers)

    def remove(self, data):
        """See `IPackageset`."""
        handlers = (
            (ISourcePackageName, self._removeSourcePackageNames),
            (IPackageset, self._removeDirectSuccessors))
        self._add_or_remove(data, handlers)

    def _add_or_remove(self, data, handlers):
        """Add or remove source package names or package sets from this one.

        :param data: an iterable with `ISourcePackageName` XOR `IPackageset`
            instances
        :param handlers: a 2-tuple Sequence where the first member is the
            interface a datum should implement and the second is the handler
            to invoke in that case respectively.
        """
        store = IMasterStore(Packageset)
        if not isinstance(data, (list, tuple)):
            data = list(data)
        count = len(data)
        for iface, handler in handlers:
            iface_data = [datum for datum in data if iface.providedBy(datum)]
            if len(iface_data) > 0:
                handler(iface_data, store)
                count -= len(iface_data)
        if count != 0:
            raise AssertionError("Not all data was handled.")

    def _addSourcePackageNames(self, source_names, store):
        """Add the given source package names to the package set.

        Souce package names already *directly* associated are ignored."""
        query = '''
            INSERT INTO packagesetsources(packageset, sourcepackagename) (
                SELECT ? AS packageset, spn.id AS sourcepackagename
                FROM sourcepackagename spn WHERE spn.id IN (%s)
                EXCEPT
                SELECT packageset, sourcepackagename FROM packagesetsources
                WHERE packageset = ?)
        ''' % ','.join(str(source_name.id) for source_name in source_names)
        store.execute(query, (self.id, self.id), noresult=True)

    def _removeSourcePackageNames(self, source_names, store):
        """Remove the given source package names from the package set."""
        query = '''
            DELETE FROM packagesetsources
            WHERE packageset = ? AND sourcepackagename IN (%s)
        ''' % ','.join(str(source_name.id) for source_name in source_names)
        store.execute(query, (self.id,), noresult=True)

    def _addDirectSuccessors(self, packagesets, store):
        """Add the given package sets as directly included subsets."""
        adsq = '''
            INSERT INTO packagesetinclusion(parent, child) (
                SELECT ? AS parent, cps.id AS child
                FROM packageset cps WHERE cps.id IN (%s)
                EXCEPT
                SELECT parent, child FROM packagesetinclusion
                WHERE parent = ?)
        ''' % ','.join(str(packageset.id) for packageset in packagesets)
        store.execute(adsq, (self.id, self.id), noresult=True)

    def _removeDirectSuccessors(self, packagesets, store):
        """Remove the given package sets as directly included subsets."""
        rdsq = '''
            DELETE FROM packagesetinclusion
            WHERE parent = ? AND child IN (%s)
        ''' % ','.join(str(packageset.id) for packageset in packagesets)
        store.execute(rdsq, (self.id,), noresult=True)

    def sourcesIncluded(self, direct_inclusion=False):
        """See `IPackageset`."""
        if direct_inclusion == False:
            source_name_query = '''
                SELECT pss.sourcepackagename
                FROM packagesetsources pss, flatpackagesetinclusion fpsi
                WHERE pss.packageset = fpsi.child AND fpsi.parent = ?
            '''
        else:
            source_name_query = '''
                SELECT pss.sourcepackagename FROM packagesetsources pss
                WHERE pss.packageset = ?
            '''
        store = IStore(Packageset)
        source_names = SQL(source_name_query, (self.id,))
        result_set = store.find(
            SourcePackageName, SourcePackageName.id.is_in(source_names))
        return _order_result_set(result_set)

    def getSourcesIncluded(self, direct_inclusion=False):
        """See `IPackageset`."""
        result_set = self.sourcesIncluded(direct_inclusion)
        return list(result_set.values(SourcePackageName.name))

    def setsIncludedBy(self, direct_inclusion=False):
        """See `IPackageset`."""
        if direct_inclusion == False:
            # The very last clause in the query is necessary because each
            # package set is also a predecessor of itself in the flattened
            # hierarchy.
            query = '''
                SELECT fpsi.parent FROM flatpackagesetinclusion fpsi
                WHERE fpsi.child = ? AND fpsi.parent != ?
            '''
            params = (self.id, self.id)
        else:
            query = '''
                SELECT psi.parent FROM packagesetinclusion psi
                WHERE psi.child = ?
            '''
            params = (self.id,)
        store = IStore(Packageset)
        predecessors = SQL(query, params)
        result_set = store.find(Packageset, Packageset.id.is_in(predecessors))
        return _order_result_set(result_set)

    def setsIncluded(self, direct_inclusion=False):
        """See `IPackageset`."""
        if direct_inclusion == False:
            # The very last clause in the query is necessary because each
            # package set is also a successor of itself in the flattened
            # hierarchy.
            query = '''
                SELECT fpsi.child FROM flatpackagesetinclusion fpsi
                WHERE fpsi.parent = ? AND fpsi.child != ?
            '''
            params = (self.id, self.id)
        else:
            query = '''
                SELECT psi.child FROM packagesetinclusion psi
                WHERE psi.parent = ?
            '''
            params = (self.id,)
        store = IStore(Packageset)
        successors = SQL(query, params)
        result_set = store.find(Packageset, Packageset.id.is_in(successors))
        return _order_result_set(result_set)

    def sourcesSharedBy(self, other_package_set, direct_inclusion=False):
        """See `IPackageset`."""
        if direct_inclusion == False:
            query = '''
                SELECT pss_this.sourcepackagename
                FROM
                    packagesetsources pss_this, packagesetsources pss_other,
                    flatpackagesetinclusion fpsi_this,
                    flatpackagesetinclusion fpsi_other
                WHERE pss_this.sourcepackagename = pss_other.sourcepackagename
                    AND pss_this.packageset = fpsi_this.child
                    AND pss_other.packageset = fpsi_other.child
                    AND fpsi_this.parent = ?  AND fpsi_other.parent = ?
            '''
        else:
            query = '''
                SELECT pss_this.sourcepackagename
                FROM packagesetsources pss_this, packagesetsources pss_other
                WHERE pss_this.sourcepackagename = pss_other.sourcepackagename
                    AND pss_this.packageset = ? AND pss_other.packageset = ?
            '''
        store = IStore(Packageset)
        source_names = SQL(query, (self.id, other_package_set.id))
        result_set = store.find(
            SourcePackageName, SourcePackageName.id.is_in(source_names))
        return _order_result_set(result_set)

    def getSourcesSharedBy(self, other_package_set, direct_inclusion=False):
        """See `IPackageset`."""
        result_set = self.sourcesSharedBy(other_package_set, direct_inclusion)
        return list(result_set.values(SourcePackageName.name))

    def sourcesNotSharedBy(self, other_package_set, direct_inclusion=False):
        """See `IPackageset`."""
        if direct_inclusion == False:
            query = '''
                SELECT pss_this.sourcepackagename
                FROM packagesetsources pss_this,
                    flatpackagesetinclusion fpsi_this
                WHERE pss_this.packageset = fpsi_this.child
                    AND fpsi_this.parent = ?
                EXCEPT
                SELECT pss_other.sourcepackagename
                FROM packagesetsources pss_other,
                    flatpackagesetinclusion fpsi_other
                WHERE pss_other.packageset = fpsi_other.child
                    AND fpsi_other.parent = ?
            '''
        else:
            query = '''
                SELECT pss_this.sourcepackagename
                FROM packagesetsources pss_this WHERE pss_this.packageset = ?
                EXCEPT
                SELECT pss_other.sourcepackagename
                FROM packagesetsources pss_other
                WHERE pss_other.packageset = ?
            '''
        store = IStore(Packageset)
        source_names = SQL(query, (self.id, other_package_set.id))
        result_set = store.find(
            SourcePackageName, SourcePackageName.id.is_in(source_names))
        return _order_result_set(result_set)

    def getSourcesNotSharedBy(
        self, other_package_set, direct_inclusion=False):
        """See `IPackageset`."""
        result_set = self.sourcesNotSharedBy(
            other_package_set, direct_inclusion)
        return list(result_set.values(SourcePackageName.name))

    def _api_add_or_remove(self, clauses, handler):
        """Look up the data to be added/removed and call the handler."""
        store = IMasterStore(Packageset)
        data = list(store.find(*clauses))
        if len(data) > 0:
            handler(data, store)

    def addSources(self, names):
        """See `IPackageset`."""
        if isinstance(names, basestring):
            names = [ensure_unicode(names)]
        clauses = (SourcePackageName, SourcePackageName.name.is_in(names))
        self._api_add_or_remove(clauses, self._addSourcePackageNames)

    def removeSources(self, names):
        """See `IPackageset`."""
        clauses = (SourcePackageName, SourcePackageName.name.is_in(names))
        self._api_add_or_remove(clauses, self._removeSourcePackageNames)

    def addSubsets(self, names):
        """See `IPackageset`."""
        clauses = (
            Packageset, Packageset.name.is_in(names),
            Packageset.distroseries == self.distroseries)
        self._api_add_or_remove(clauses, self._addDirectSuccessors)

    def removeSubsets(self, names):
        """See `IPackageset`."""
        clauses = (
            Packageset, Packageset.name.is_in(names),
            Packageset.distroseries == self.distroseries)
        self._api_add_or_remove(clauses, self._removeDirectSuccessors)

    def relatedSets(self):
        """See `IPackageset`."""
        store = IStore(Packageset)
        result_set = store.find(
            Packageset,
            Packageset.packagesetgroup == self.packagesetgroup,
            Packageset.id != self.id)
        return _order_result_set(result_set)

    def destroySelf(self):
        store = IStore(Packageset)
        sources = store.find(
            PackagesetSources,
            PackagesetSources.packageset == self)
        sources.remove()
        store.remove(self)
        if self.relatedSets().is_empty():
            store.remove(self.packagesetgroup)


class PackagesetSet:
    """See `IPackagesetSet`."""
    implements(IPackagesetSet)

    def new(
        self, name, description, owner, distroseries=None, related_set=None):
        """See `IPackagesetSet`."""
        store = IMasterStore(Packageset)

        packagesetgroup = None
        if related_set is not None:
            # Use the packagesetgroup of the `related_set`.
            packagesetgroup = related_set.packagesetgroup
        else:
            # We create the related internal PackagesetGroup for this
            # packageset so that we can later see related package sets across
            # distroseries.
            packagesetgroup = PackagesetGroup()
            packagesetgroup.owner = owner
            store.add(packagesetgroup)

        if distroseries is None:
            ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
            distroseries = ubuntu.currentseries

        packageset = Packageset()
        packageset.packagesetgroup = packagesetgroup
        packageset.name = name
        packageset.description = description
        packageset.owner = owner

        packageset.distroseries = distroseries

        store.add(packageset)

        # We need to ensure that the cached statements are flushed so that
        # the duplicate name constraint gets triggered here.
        try:
            store.flush()
        except IntegrityError:
            raise DuplicatePackagesetName()

        return packageset

    def __getitem__(self, name):
        """See `IPackagesetSet`."""
        return self.getByName(name)

    def getByName(self, name, distroseries=None):
        """See `IPackagesetSet`."""
        store = IStore(Packageset)
        if not isinstance(name, unicode):
            name = unicode(name, 'utf-8')

        ubuntu = getUtility(IDistributionSet).getByName(u'ubuntu')
        extra_args = []
        if distroseries is not None:
            # If the user just passed a distro series name, look it up.
            if isinstance(distroseries, basestring):
                try:
                    distroseries = ubuntu[distroseries]
                except NotFoundError:
                    raise NoSuchPackageSet(distroseries)
            extra_args.append(Packageset.distroseries == distroseries)
        else:
            extra_args.append(Packageset.distroseries == ubuntu.currentseries)

        package_set = store.find(
            Packageset, Packageset.name == name, *extra_args).one()

        if package_set is None:
            raise NoSuchPackageSet(name)

        return package_set

    def getByOwner(self, owner):
        """See `IPackagesetSet`."""
        store = IStore(Packageset)
        result_set = store.find(Packageset, Packageset.owner == owner)
        return _order_result_set(result_set)

    def getBySeries(self, distroseries):
        """See `IPackagesetSet`."""
        store = IStore(Packageset)
        result_set = store.find(
            Packageset, Packageset.distroseries == distroseries)
        return _order_result_set(result_set)

    def get(self):
        """See `IPackagesetSet`."""
        store = IStore(Packageset)
        result_set = store.find(Packageset)
        return _order_result_set(result_set)

    def _nameToSourcePackageName(self, source_name):
        """Helper to convert a possible string name to ISourcePackageName."""
        if isinstance(source_name, basestring):
            source_name = getUtility(ISourcePackageNameSet)[source_name]
        return source_name

    def getForPackages(self, distroseries, sourcepackagename_ids):
        """See `IPackagesetSet`."""
        tuples = IStore(Packageset).find(
            (PackagesetSources.sourcepackagename_id, Packageset),
            Packageset.id == PackagesetSources.packageset_id,
            Packageset.distroseries == distroseries,
            PackagesetSources.sourcepackagename_id.is_in(
                sourcepackagename_ids))
        packagesets_by_package = {}
        for package, packageset in tuples:
            packagesets_by_package.setdefault(package, []).append(packageset)
        return packagesets_by_package

    def setsIncludingSource(self, sourcepackagename, distroseries=None,
                            direct_inclusion=False):
        """See `IPackagesetSet`."""
        sourcepackagename = self._nameToSourcePackageName(sourcepackagename)

        if direct_inclusion:
            query = '''
                SELECT pss.packageset FROM packagesetsources pss
                WHERE pss.sourcepackagename = ?
            '''
        else:
            query = '''
                SELECT fpsi.parent
                FROM packagesetsources pss, flatpackagesetinclusion fpsi
                WHERE pss.sourcepackagename = ?
                AND pss.packageset = fpsi.child
            '''
        store = IStore(Packageset)
        psets = SQL(query, (sourcepackagename.id,))
        clauses = [Packageset.id.is_in(psets)]
        if distroseries:
            clauses.append(Packageset.distroseries == distroseries)

        result_set = store.find(Packageset, *clauses)
        return _order_result_set(result_set)
