# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Retirement of packages that are removed upstream."""

__metaclass__ = type
__all__ = [
    'dominate_imported_source_packages',
    ]

from zope.component import getUtility

from lp.archivepublisher.domination import Dominator
from lp.registry.interfaces.distribution import IDistributionSet


def dominate_imported_source_packages(txn, logger, distro_name, series_name,
                                      pocket, packages_map):
    """Perform domination."""
    series = getUtility(IDistributionSet)[distro_name].getSeries(series_name)
    dominator = Dominator(logger, series.main_archive)

    # Dominate all packages published in the series.  This includes all
    # packages listed in the Sources file we imported, but also packages
    # that have been recently deleted.
    package_counts = dominator.findPublishedSourcePackageNames(series, pocket)
    for package_name, pub_count in package_counts:
        entries = packages_map.src_map.get(package_name, [])
        live_versions = [
            entry['Version'] for entry in entries if 'Version' in entry]

        # Gina import just ensured that any live version in the Sources
        # file has a Published publication.  So there should be at least
        # as many Published publications as live versions.
        if pub_count < len(live_versions):
            logger.warn(
                "Package %s has fewer live source publications (%s) than "
                "live versions (%s).  The archive may be broken in some "
                "way.",
                package_name, pub_count, len(live_versions))

        # Domination can only turn Published publications into
        # non-Published ones, and ensures that we end up with one
        # Published publication per live version.  Thus, if there are as
        # many Published publications as live versions, there is no
        # domination to do.  We skip these as an optimization.  Without
        # it, dominating a single Debian series takes hours.
        if pub_count != len(live_versions):
            logger.debug("Dominating %s.", package_name)
            dominator.dominateSourceVersions(
                series, pocket, package_name, live_versions)
            txn.commit()
        else:
            logger.debug2(
                "Skipping domination for %s: %d live version(s) and "
                "publication(s).", package_name, pub_count)
