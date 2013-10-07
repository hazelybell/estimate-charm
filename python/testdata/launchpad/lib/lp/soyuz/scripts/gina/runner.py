# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'run_gina',
    ]

import sys
import time

import psycopg2
from zope.component import getUtility

from lp.services.config import config
from lp.services.features import getFeatureFlag
from lp.services.scripts import log
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.scripts.gina import ExecutionError
from lp.soyuz.scripts.gina.archive import (
    ArchiveComponentItems,
    MangledArchiveError,
    PackagesMap,
    )
from lp.soyuz.scripts.gina.dominate import dominate_imported_source_packages
from lp.soyuz.scripts.gina.handlers import (
    DataSetupError,
    ImporterHandler,
    MultiplePackageReleaseError,
    NoSourcePackageError,
    )
from lp.soyuz.scripts.gina.packages import (
    BinaryPackageData,
    DisplayNameDecodingError,
    InvalidVersionError,
    MissingRequiredArguments,
    PoolFileNotFound,
    SourcePackageData,
    )


def run_gina(options, ztm, target_section):
    # Avoid circular imports.
    from lp.registry.interfaces.pocket import PackagePublishingPocket

    package_root = target_section.root
    distro = target_section.distro
    pocket_distroseries = target_section.pocketrelease
    distroseries = target_section.distroseries
    components = [c.strip() for c in target_section.components.split(",")]
    archs = [a.strip() for a in target_section.architectures.split(",")]
    pocket = target_section.pocket
    component_override = target_section.componentoverride
    source_only = target_section.source_only
    spnames_only = target_section.sourcepackagenames_only

    LIBRHOST = config.librarian.upload_host
    LIBRPORT = config.librarian.upload_port

    log.info("")
    log.info("=== Processing %s/%s/%s ===", distro, distroseries, pocket)
    log.debug("Packages read from: %s", package_root)
    log.info("Components to import: %s", ", ".join(components))
    if component_override is not None:
        log.info("Override components to: %s", component_override)
    log.info("Architectures to import: %s", ", ".join(archs))
    log.debug("Launchpad database: %s", config.database.rw_main_master)
    log.info("SourcePackage Only: %s", source_only)
    log.info("SourcePackageName Only: %s", spnames_only)
    log.debug("Librarian: %s:%s", LIBRHOST, LIBRPORT)
    log.info("")

    if not hasattr(PackagePublishingPocket, pocket.upper()):
        log.error("Could not find a pocket schema for %s", pocket)
        sys.exit(1)

    pocket = getattr(PackagePublishingPocket, pocket.upper())

    if component_override:
        valid_components = [
            component.name for component in getUtility(IComponentSet)]
        if component_override not in valid_components:
            log.error("Could not find component %s", component_override)
            sys.exit(1)

    try:
        arch_component_items = ArchiveComponentItems(
            package_root, pocket_distroseries, components, archs,
            source_only)
    except MangledArchiveError:
        log.exception(
            "Failed to analyze archive for %s", pocket_distroseries)
        sys.exit(1)

    packages_map = PackagesMap(arch_component_items)
    importer_handler = ImporterHandler(
        ztm, distro, distroseries, package_root, pocket, component_override)

    import_sourcepackages(distro, packages_map, package_root, importer_handler)
    importer_handler.commit()

    # XXX JeroenVermeulen 2011-09-07 bug=843728: Dominate binaries as well.
    dominate_imported_source_packages(
        ztm, log, distro, distroseries, pocket, packages_map)
    ztm.commit()

    if source_only:
        log.info('Source only mode... done')
        return

    for archtag in archs:
        try:
            importer_handler.ensure_archinfo(archtag)
        except DataSetupError:
            log.exception("Database setup required for run on %s", archtag)
            sys.exit(1)

    import_binarypackages(distro, packages_map, package_root, importer_handler)
    importer_handler.commit()


def attempt_source_package_import(distro, source, package_root,
                                  importer_handler):
    """Attempt to import a source package, and handle typical errors."""
    package_name = source.get("Package", "unknown")
    try:
        try:
            do_one_sourcepackage(
                distro, source, package_root, importer_handler)
        except psycopg2.Error:
            log.exception(
                "Database error: unable to create SourcePackage for %s. "
                "Retrying once..", package_name)
            importer_handler.abort()
            time.sleep(15)
            do_one_sourcepackage(
                distro, source, package_root, importer_handler)
    except (
        InvalidVersionError, MissingRequiredArguments,
        DisplayNameDecodingError):
        log.exception(
            "Unable to create SourcePackageData for %s", package_name)
    except (PoolFileNotFound, ExecutionError):
        # Problems with katie db stuff of opening files
        log.exception("Error processing package files for %s", package_name)
    except psycopg2.Error:
        log.exception(
            "Database errors made me give up: unable to create "
            "SourcePackage for %s", package_name)
        importer_handler.abort()
    except MultiplePackageReleaseError:
        log.exception(
            "Database duplication processing %s", package_name)


def import_sourcepackages(distro, packages_map, package_root,
                          importer_handler):
    # Goes over src_map importing the sourcepackages packages.
    npacks = len(packages_map.src_map)
    log.info('%i Source Packages to be imported', npacks)

    for package in sorted(packages_map.src_map.iterkeys()):
        for source in packages_map.src_map[package]:
            attempt_source_package_import(
                distro, source, package_root, importer_handler)


def do_one_sourcepackage(distro, source, package_root, importer_handler):
    source_data = SourcePackageData(**source)
    skip_key = u'%s/%s/%s' % (distro, source_data.package, source_data.version)
    skip_list = getFeatureFlag('soyuz.gina.skip_source_versions')
    if skip_list is not None and skip_key in skip_list.split():
        log.info(
            "Skipping %s %s as requested by feature flag.",
            source_data.package, source_data.version)
        return
    if importer_handler.preimport_sourcecheck(source_data):
        # Don't bother reading package information if the source package
        # already exists in the database
        log.info('%s already exists in the archive', source_data.package)
        return
    source_data.process_package(distro, package_root)
    source_data.ensure_complete()
    importer_handler.import_sourcepackage(source_data)
    importer_handler.commit()


def import_binarypackages(distro, packages_map, package_root,
                          importer_handler):
    nosource = []

    # Run over all the architectures we have
    for archtag in packages_map.bin_map.keys():
        npacks = len(packages_map.bin_map[archtag])
        log.info(
            '%i Binary Packages to be imported for %s', npacks, archtag)
        # Go over binarypackages importing them for this architecture
        for package_name in sorted(packages_map.bin_map[archtag].iterkeys()):
            binary = packages_map.bin_map[archtag][package_name]
            try:
                try:
                    do_one_binarypackage(
                        distro, binary, archtag, package_root,
                        importer_handler)
                except psycopg2.Error:
                    log.exception(
                        "Database errors when importing a BinaryPackage "
                        "for %s. Retrying once..", package_name)
                    importer_handler.abort()
                    time.sleep(15)
                    do_one_binarypackage(
                        distro, binary, archtag, package_root,
                        importer_handler)
            except (InvalidVersionError, MissingRequiredArguments):
                log.exception(
                    "Unable to create BinaryPackageData for %s", package_name)
                continue
            except (PoolFileNotFound, ExecutionError):
                # Problems with katie db stuff of opening files
                log.exception(
                    "Error processing package files for %s", package_name)
                continue
            except MultiplePackageReleaseError:
                log.exception(
                    "Database duplication processing %s", package_name)
                continue
            except psycopg2.Error:
                log.exception(
                    "Database errors made me give up: unable to create "
                    "BinaryPackage for %s", package_name)
                importer_handler.abort()
                continue
            except NoSourcePackageError:
                log.exception(
                    "Failed to create Binary Package for %s", package_name)
                nosource.append(binary)
                continue

        if nosource:
            # XXX kiko 2005-10-23: untested
            log.warn('%i source packages not found', len(nosource))
            for pkg in nosource:
                log.warn(pkg)


def do_one_binarypackage(distro, binary, archtag, package_root,
                         importer_handler):
    binary_data = BinaryPackageData(**binary)
    if importer_handler.preimport_binarycheck(archtag, binary_data):
        log.info('%s already exists in the archive', binary_data.package)
        return
    binary_data.process_package(distro, package_root)
    importer_handler.import_binarypackage(archtag, binary_data)
    importer_handler.commit()
