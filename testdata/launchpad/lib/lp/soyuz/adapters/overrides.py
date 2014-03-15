# Copyright 2011-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Generic Override Policy classes."""

__metaclass__ = type

__all__ = [
    'BinaryOverride',
    'FromExistingOverridePolicy',
    'IBinaryOverride',
    'ISourceOverride',
    'SourceOverride',
    'UbuntuOverridePolicy',
    'UnknownOverridePolicy',
    ]


from storm.expr import (
    And,
    Desc,
    Or,
    )
from zope.component import getUtility
from zope.interface import (
    Attribute,
    implements,
    Interface,
    )

from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.database import bulk
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.interfaces import IStore
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.model.binarypackagename import BinaryPackageName
from lp.soyuz.model.component import Component
from lp.soyuz.model.distroarchseries import DistroArchSeries
from lp.soyuz.model.publishing import (
    BinaryPackagePublishingHistory,
    SourcePackagePublishingHistory,
    )
from lp.soyuz.model.section import Section


class IOverride(Interface):
    """Override data class.

    This class represents all the basic overridable data on a publication.
    """

    component = Attribute("The IComponent override")
    section = Attribute("The ISection override")


class ISourceOverride(IOverride):
    """Source-specific overrides on a publication."""

    source_package_name = Attribute(
        "The ISourcePackageName that's being overridden")


class IBinaryOverride(IOverride):
    """Binary-specific overrides on a publication."""

    binary_package_name = Attribute(
        "The IBinaryPackageName that's being overridden")
    distro_arch_series = Attribute(
        "The IDistroArchSeries for the publication")
    priority = Attribute(
        "The PackagePublishingPriority that's being overridden")
    phased_update_percentage = Attribute(
        "The phased update percentage that's being overridden")


class Override:
    """See `IOverride`."""

    def __init__(self, component, section):
        self.component = component
        self.section = section

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        # Prevent people getting very confused with these new classes,
        # should their instances ever be put in a dict or set.
        raise NotImplementedError(
            "%s objects are not hashable." % self.__class__.__name__)


class SourceOverride(Override):
    """See `ISourceOverride`."""
    implements(ISourceOverride)

    def __init__(self, source_package_name, component, section):
        super(SourceOverride, self).__init__(component, section)
        self.source_package_name = source_package_name

    def __eq__(self, other):
        return (
            self.source_package_name == other.source_package_name and
            self.component == other.component and
            self.section == other.section)


class BinaryOverride(Override):
    """See `IBinaryOverride`."""
    implements(IBinaryOverride)

    def __init__(self, binary_package_name, distro_arch_series, component,
                 section, priority, phased_update_percentage):
        super(BinaryOverride, self).__init__(component, section)
        self.binary_package_name = binary_package_name
        self.distro_arch_series = distro_arch_series
        self.priority = priority
        self.phased_update_percentage = phased_update_percentage

    def __eq__(self, other):
        return (
            self.binary_package_name == other.binary_package_name and
            self.distro_arch_series == other.distro_arch_series and
            self.component == other.component and
            self.section == other.section and
            self.priority == other.priority and
            self.phased_update_percentage == other.phased_update_percentage)

    def __repr__(self):
        return ("<BinaryOverride at %x component=%r section=%r "
            "binary_package_name=%r distro_arch_series=%r priority=%r "
            "phased_update_percentage=%r>" %
            (id(self), self.component, self.section, self.binary_package_name,
             self.distro_arch_series, self.priority,
             self.phased_update_percentage))


class IOverridePolicy(Interface):
    """Override policy.

    An override policy returns overrides suitable for the given archive,
    distroseries, pocket for source or binary publications.

    For example, an implementation might allow existing publications to
    keep the same component and section as their ancestor publications.
    """

    phased_update_percentage = Attribute(
        "The phased update percentage to apply to binary publications.")

    def calculateSourceOverrides(archive, distroseries, pocket, sources,
                                 source_component=None):
        """Calculate source overrides.

        :param archive: The target `IArchive`.
        :param distroseries: The target `IDistroSeries`.
        :param pocket: The target `PackagePublishingPocket`.
        :param sources: A tuple of `ISourcePackageName`s.
        :param source_component: The sources' `IComponent` (optional).

        :return: A list of `ISourceOverride`
        """
        pass

    def calculateBinaryOverrides(archive, distroseries, pocket, binaries):
        """Calculate binary overrides.

        :param archive: The target `IArchive`.
        :param distroseries: The target `IDistroSeries`.
        :param pocket: The target `PackagePublishingPocket`.
        :param binaries: A tuple of `IBinaryPackageName`, architecturetag
            pairs. Architecturetag can be None for architecture-independent
            publications.

        :return: A list of `IBinaryOverride`
        """
        pass


class BaseOverridePolicy:

    implements(IOverridePolicy)

    def __init__(self, phased_update_percentage=None):
        super(BaseOverridePolicy, self).__init__()
        self.phased_update_percentage = phased_update_percentage

    def calculateSourceOverrides(self, archive, distroseries, pocket,
                                 sources, source_component=None):
        raise NotImplementedError()

    def calculateBinaryOverrides(self, archive, distroseries, pocket,
                                 binaries):
        raise NotImplementedError()


class FromExistingOverridePolicy(BaseOverridePolicy):
    """Override policy that only searches for existing publications.

    Override policy that returns the SourcePackageName, component and
    section for the latest published source publication, or the
    BinaryPackageName, DistroArchSeries, component, section and priority
    for the latest published binary publication.
    """

    def getExistingPublishingStatuses(self, include_deleted):
        status = [
            PackagePublishingStatus.PENDING,
            PackagePublishingStatus.PUBLISHED,
            ]
        if include_deleted:
            status.append(PackagePublishingStatus.DELETED)
        return status

    def calculateSourceOverrides(self, archive, distroseries, pocket, spns,
                                 source_component=None, include_deleted=False):
        def eager_load(rows):
            bulk.load(Component, (row[1] for row in rows))
            bulk.load(Section, (row[2] for row in rows))

        store = IStore(SourcePackagePublishingHistory)
        already_published = DecoratedResultSet(
            store.find(
                (SourcePackagePublishingHistory.sourcepackagenameID,
                 SourcePackagePublishingHistory.componentID,
                 SourcePackagePublishingHistory.sectionID),
                SourcePackagePublishingHistory.archiveID == archive.id,
                SourcePackagePublishingHistory.distroseriesID ==
                    distroseries.id,
                SourcePackagePublishingHistory.status.is_in(
                    self.getExistingPublishingStatuses(include_deleted)),
                SourcePackagePublishingHistory.sourcepackagenameID.is_in(
                    spn.id for spn in spns)).order_by(
                        SourcePackagePublishingHistory.sourcepackagenameID,
                        Desc(SourcePackagePublishingHistory.datecreated),
                        Desc(SourcePackagePublishingHistory.id),
                ).config(
                    distinct=(
                        SourcePackagePublishingHistory.sourcepackagenameID,)),
            id_resolver((SourcePackageName, Component, Section)),
            pre_iter_hook=eager_load)
        return [
            SourceOverride(name, component, section)
            for (name, component, section) in already_published]

    def calculateBinaryOverrides(self, archive, distroseries, pocket,
                                 binaries, include_deleted=False):
        def eager_load(rows):
            bulk.load(Component, (row[2] for row in rows))
            bulk.load(Section, (row[3] for row in rows))

        store = IStore(BinaryPackagePublishingHistory)
        expanded = calculate_target_das(distroseries, binaries)

        candidates = [
            make_package_condition(archive, das, bpn)
            for bpn, das in expanded if das is not None]
        if len(candidates) == 0:
            return []
        # Do not copy phased_update_percentage from existing publications;
        # it is too context-dependent to copy.
        already_published = DecoratedResultSet(
            store.find(
                (BinaryPackagePublishingHistory.binarypackagenameID,
                 BinaryPackagePublishingHistory.distroarchseriesID,
                 BinaryPackagePublishingHistory.componentID,
                 BinaryPackagePublishingHistory.sectionID,
                 BinaryPackagePublishingHistory.priority),
                BinaryPackagePublishingHistory.status.is_in(
                    self.getExistingPublishingStatuses(include_deleted)),
                Or(*candidates)).order_by(
                    BinaryPackagePublishingHistory.distroarchseriesID,
                    BinaryPackagePublishingHistory.binarypackagenameID,
                    Desc(BinaryPackagePublishingHistory.datecreated),
                    Desc(BinaryPackagePublishingHistory.id),
                ).config(distinct=(
                    BinaryPackagePublishingHistory.distroarchseriesID,
                    BinaryPackagePublishingHistory.binarypackagenameID,
                    )
                ),
            id_resolver(
                (BinaryPackageName, DistroArchSeries, Component, Section,
                None)),
            pre_iter_hook=eager_load)
        return [
            BinaryOverride(
                name, das, component, section, priority,
                self.phased_update_percentage)
            for name, das, component, section, priority in already_published]


class UnknownOverridePolicy(BaseOverridePolicy):
    """Override policy that returns defaults.

    Override policy that assumes everything passed in doesn't exist, so
    returns the defaults.

    Newly-uploaded files have a default set of overrides to be applied.
    This reduces the amount of work that archive admins have to do
    since they override the majority of new uploads with the same
    values.  The rules for overriding are: (See bug #120052)
        'contrib' -> 'multiverse'
        'non-free' -> 'multiverse'
        everything else -> 'universe'
    This mainly relates to Debian syncs, where the default component
    is 'main' but should not be in main for Ubuntu.
    """

    DEBIAN_COMPONENT_OVERRIDE_MAP = {
        'contrib': 'multiverse',
        'non-free': 'multiverse',
        }

    DEFAULT_OVERRIDE_COMPONENT = 'universe'

    @classmethod
    def getComponentOverride(cls, component=None, return_component=False):
        # component can be a Component object or a component name.
        if isinstance(component, Component):
            component = component.name
        override_component_name = cls.DEBIAN_COMPONENT_OVERRIDE_MAP.get(
            component, cls.DEFAULT_OVERRIDE_COMPONENT)
        if return_component:
            return getUtility(IComponentSet)[override_component_name]
        else:
            return override_component_name

    def calculateSourceOverrides(self, archive, distroseries, pocket,
                                 sources, source_component=None):
        default_component = (
            archive.default_component or
            UnknownOverridePolicy.getComponentOverride(
                source_component, return_component=True))
        return [
            SourceOverride(source, default_component, None)
            for source in sources]

    def calculateBinaryOverrides(self, archive, distroseries, pocket,
                                 binaries):
        default_component = archive.default_component or getUtility(
            IComponentSet)['universe']
        return [
            BinaryOverride(
                binary, das, default_component, None, None,
                self.phased_update_percentage)
            for binary, das in calculate_target_das(distroseries, binaries)]


class UbuntuOverridePolicy(FromExistingOverridePolicy,
                           UnknownOverridePolicy):
    """Override policy for Ubuntu.

    An override policy that incorporates both the existing policy and the
    unknown policy.
    """

    def calculateSourceOverrides(self, archive, distroseries, pocket,
                                 sources, source_component=None):
        total = set(sources)
        overrides = FromExistingOverridePolicy.calculateSourceOverrides(
            self, archive, distroseries, pocket, sources, source_component,
            include_deleted=True)
        existing = set(override.source_package_name for override in overrides)
        missing = total.difference(existing)
        if missing:
            unknown = UnknownOverridePolicy.calculateSourceOverrides(
                self, archive, distroseries, pocket, missing, source_component)
            overrides.extend(unknown)
        return overrides

    def calculateBinaryOverrides(self, archive, distroseries, pocket,
                                 binaries):
        total = set(binaries)
        overrides = FromExistingOverridePolicy.calculateBinaryOverrides(
            self, archive, distroseries, pocket, binaries,
            include_deleted=True)
        existing = set(
            (
                override.binary_package_name,
                override.distro_arch_series.architecturetag,
            )
            for override in overrides)
        missing = total.difference(existing)
        if missing:
            unknown = UnknownOverridePolicy.calculateBinaryOverrides(
                self, archive, distroseries, pocket, missing)
            overrides.extend(unknown)
        return overrides


def calculate_target_das(distroseries, binaries):
    arch_map = dict(
        (arch.architecturetag, arch)
        for arch in distroseries.enabled_architectures)

    with_das = []
    for bpn, archtag in binaries:
        if archtag is not None:
            with_das.append((bpn, arch_map.get(archtag)))
        else:
            with_das.append((bpn, distroseries.nominatedarchindep))
    return with_das


def make_package_condition(archive, das, bpn):
    return And(
        BinaryPackagePublishingHistory.archiveID == archive.id,
        BinaryPackagePublishingHistory.distroarchseriesID == das.id,
        BinaryPackagePublishingHistory.binarypackagenameID == bpn.id)


def id_resolver(lookups):
    def _resolve(row):
        store = IStore(SourcePackagePublishingHistory)
        return tuple(
            (value if cls is None else store.get(cls, value))
            for value, cls in zip(row, lookups))

    return _resolve
