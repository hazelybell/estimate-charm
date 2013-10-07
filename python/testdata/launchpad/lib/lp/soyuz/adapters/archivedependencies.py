# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Archive dependencies helper function.

This module contains the static maps representing the 'layered' component
and pocket dependencies and helper function to handler `ArchiveDependency`
records.

 * component_dependencies: static map of component dependencies
 * pocket_dependencies: static map of pocket dependencies

Auxiliary functions exposed for testing purposes:

 * get_components_for_context: return the corresponding component
       dependencies for a component and pocket, this result is known as
       'ogre_components';
 * get_primary_current_component: return the component name where the
       building source is published in the primary archive.

`sources_list` content generation.

 * get_sources_list_for_building: return a list of `sources_list` lines
       that should be used to build the given `IBuild`.

"""

__metaclass__ = type

__all__ = [
    'component_dependencies',
    'default_component_dependency_name',
    'default_pocket_dependency',
    'expand_dependencies',
    'get_components_for_context',
    'get_primary_current_component',
    'get_sources_list_for_building',
    'pocket_dependencies',
    ]

import logging
import traceback

from lazr.uri import URI
from zope.component import getUtility

from lp.app.errors import NotFoundError
from lp.registry.interfaces.distroseriesparent import IDistroSeriesParentSet
from lp.registry.interfaces.pocket import (
    PackagePublishingPocket,
    pocketsuffix,
    )
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.archive import ALLOW_RELEASE_BUILDS


component_dependencies = {
    'main': ['main'],
    'restricted': ['main', 'restricted'],
    'universe': ['main', 'universe'],
    'multiverse': ['main', 'restricted', 'universe', 'multiverse'],
    'partner': ['partner'],
    }

pocket_dependencies = {
    PackagePublishingPocket.RELEASE: (
        PackagePublishingPocket.RELEASE,
        ),
    PackagePublishingPocket.SECURITY: (
        PackagePublishingPocket.RELEASE,
        PackagePublishingPocket.SECURITY,
        ),
    PackagePublishingPocket.UPDATES: (
        PackagePublishingPocket.RELEASE,
        PackagePublishingPocket.SECURITY,
        PackagePublishingPocket.UPDATES,
        ),
    PackagePublishingPocket.BACKPORTS: (
        PackagePublishingPocket.RELEASE,
        PackagePublishingPocket.SECURITY,
        PackagePublishingPocket.UPDATES,
        PackagePublishingPocket.BACKPORTS,
        ),
    PackagePublishingPocket.PROPOSED: (
        PackagePublishingPocket.RELEASE,
        PackagePublishingPocket.SECURITY,
        PackagePublishingPocket.UPDATES,
        PackagePublishingPocket.PROPOSED,
        ),
    }

default_pocket_dependency = PackagePublishingPocket.UPDATES

default_component_dependency_name = 'multiverse'


def get_components_for_context(component, pocket):
    """Return the components allowed to be used in the build context.

    :param component: the context `IComponent`.
    :param pocket: the context `IPocket`.
    :return: a list of component names.
    """
    # BACKPORTS should be able to fetch build dependencies from any
    # component in order to cope with component changes occurring
    # across distroseries. See bug #198936 for further information.
    if pocket == PackagePublishingPocket.BACKPORTS:
        return component_dependencies['multiverse']

    return component_dependencies[component.name]


def get_primary_current_component(archive, distroseries, sourcepackagename):
    """Return the component name of the primary archive ancestry.

    If no ancestry could be found, default to 'universe'.
    """
    primary_archive = archive.distribution.main_archive
    ancestries = primary_archive.getPublishedSources(
        name=sourcepackagename,
        distroseries=distroseries, exact_match=True)

    try:
        return ancestries[0].component.name
    except IndexError:
        return 'universe'


def expand_dependencies(archive, distro_arch_series, pocket, component,
                        source_package_name):
    """Return the set of dependency archives, pockets and components.

    :param archive: the context `IArchive`.
    :param distro_arch_series: the context `IDistroArchSeries`.
    :param pocket: the context `PackagePublishingPocket`.
    :param component: the context `IComponent`.
    :param source_package_name: A source package name (as text)
    :return: a list of (archive, distro_arch_series, pocket, [component]),
        representing the dependencies defined by the given build context.
    """
    distro_series = distro_arch_series.distroseries
    deps = []

    # Add implicit self-dependency for non-primary contexts.
    if archive.purpose in ALLOW_RELEASE_BUILDS:
        deps.append((
            archive, distro_arch_series, PackagePublishingPocket.RELEASE,
            get_components_for_context(component, pocket)))

    primary_component = get_primary_current_component(
        archive, distro_series, source_package_name)
    # Consider user-selected archive dependencies.
    for archive_dependency in archive.dependencies:
        # When the dependency component is undefined, we should use
        # the component where the source is published in the primary
        # archive.
        if archive_dependency.component is None:
            components = component_dependencies[primary_component]
        else:
            components = component_dependencies[
                archive_dependency.component.name]
        # Follow pocket dependencies.
        for pocket in pocket_dependencies[archive_dependency.pocket]:
            deps.append(
                (archive_dependency.dependency, distro_arch_series, pocket,
                 components))

    # Consider primary archive dependency override. Add the default
    # primary archive dependencies if it's not present.
    if archive.getArchiveDependency(
        archive.distribution.main_archive) is None:
        primary_dependencies = _get_default_primary_dependencies(
            archive, distro_arch_series, component, pocket)
        deps.extend(primary_dependencies)

    # Add dependencies for overlay archives defined in DistroSeriesParent.
    # This currently only applies for derived distributions but in the future
    # should be merged with ArchiveDependency so we don't have two separate
    # tables essentially doing the same thing.
    dsp_set = getUtility(IDistroSeriesParentSet)
    for dsp in dsp_set.getFlattenedOverlayTree(distro_series):
        try:
            dep_arch_series = dsp.parent_series.getDistroArchSeries(
                distro_arch_series.architecturetag)
            dep_archive = dsp.parent_series.distribution.main_archive
            components = component_dependencies[dsp.component.name]
            # Follow pocket dependencies.
            for pocket in pocket_dependencies[dsp.pocket]:
                deps.append(
                    (dep_archive, dep_arch_series, pocket, components))
        except NotFoundError:
            pass

    return deps


def get_sources_list_for_building(build, distroarchseries, sourcepackagename):
    """Return the sources_list entries required to build the given item.

    The entries are returned in the order that is most useful;
     1. the context archive itself
     2. external dependencies
     3. user-selected archive dependencies
     4. the default primary archive

    :param build: a context `IBuild`.
    :param distroarchseries: A `IDistroArchSeries`
    :param sourcepackagename: A source package name (as text)
    :return: a deb sources_list entries (lines).
    """
    deps = expand_dependencies(
        build.archive, distroarchseries, build.pocket,
        build.current_component, sourcepackagename)
    sources_list_lines = \
        _get_sources_list_for_dependencies(deps)

    external_dep_lines = []
    # Append external sources_list lines for this archive if it's
    # specified in the configuration.
    try:
        dependencies = build.archive.external_dependencies
        if dependencies is not None:
            for archive_dep in dependencies.splitlines():
                line = archive_dep % (
                    {'series': distroarchseries.distroseries.name})
                external_dep_lines.append(line)
    except StandardError:
        # Malformed external dependencies can incapacitate the build farm
        # manager (lp:516169). That's obviously not acceptable.
        # Log the error, and disable the PPA.
        logger = logging.getLogger()
        logger.error(
            'Exception during external dependency processing:\n%s'
            % traceback.format_exc())
        # Disable the PPA if needed. This will suspend all the pending binary
        # builds associated with the problematic PPA.
        if build.archive.enabled == True:
            build.archive.disable()

    # For an unknown reason (perhaps because OEM has archives with
    # binaries that need to override primary binaries of the same
    # version), we want the external dependency lines to show up second:
    # after the archive itself, but before any other dependencies.
    return [sources_list_lines[0]] + external_dep_lines + \
           sources_list_lines[1:]


def _has_published_binaries(archive, distroarchseries, pocket):
    """Whether or not the archive dependency has published binaries."""
    # The primary archive dependencies are always relevant.
    if archive.purpose == ArchivePurpose.PRIMARY:
        return True

    published_binaries = archive.getAllPublishedBinaries(
        distroarchseries=distroarchseries,
        status=PackagePublishingStatus.PUBLISHED)
    return not published_binaries.is_empty()


def _get_binary_sources_list_line(archive, distroarchseries, pocket,
                                  components):
    """Return the correponding binary sources_list line."""
    # Encode the private PPA repository password in the
    # sources_list line. Note that the buildlog will be
    # sanitized to not expose it.
    if archive.private:
        uri = URI(archive.archive_url)
        uri = uri.replace(
            userinfo="buildd:%s" % archive.buildd_secret)
        url = str(uri)
    else:
        url = archive.archive_url

    suite = distroarchseries.distroseries.name + pocketsuffix[pocket]
    return 'deb %s %s %s' % (url, suite, ' '.join(components))


def _get_sources_list_for_dependencies(dependencies):
    """Return a list of sources_list lines.

    Process the given list of dependency tuples for the given
    `DistroArchseries`.

    :param dependencies: list of 3 elements tuples as:
        (`IArchive`, `IDistroArchSeries`, `PackagePublishingPocket`,
         list of `IComponent` names)
    :param distroarchseries: target `IDistroArchSeries`;

    :return: a list of sources_list formatted lines.
    """
    sources_list_lines = []
    for archive, distro_arch_series, pocket, components in dependencies:
        has_published_binaries = _has_published_binaries(
            archive, distro_arch_series, pocket)
        if not has_published_binaries:
            continue
        sources_list_line = _get_binary_sources_list_line(
            archive, distro_arch_series, pocket, components)
        sources_list_lines.append(sources_list_line)

    return sources_list_lines


def _get_default_primary_dependencies(archive, distro_series, component,
                                      pocket):
    """Return the default primary dependencies for a given context.

    :param archive: the context `IArchive`.
    :param distro_series: the context `IDistroSeries`.
    :param component: the context `IComponent`.
    :param pocket: the context `PackagePublishingPocket`.

    :return: a list containing the default dependencies to primary
        archive.
    """
    if archive.purpose in ALLOW_RELEASE_BUILDS:
        primary_pockets = pocket_dependencies[
            default_pocket_dependency]
        primary_components = component_dependencies[
            default_component_dependency_name]
    else:
        primary_pockets = pocket_dependencies[pocket]
        primary_components = get_components_for_context(component, pocket)

    primary_dependencies = []
    for pocket in primary_pockets:
        primary_dependencies.append(
            (archive.distribution.main_archive, distro_series, pocket,
             primary_components))

    return primary_dependencies
