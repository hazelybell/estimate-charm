#!/usr/bin/python
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import sqlvalues
from lp.services.scripts.base import LaunchpadCronScript
from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.model.archive import Archive

# PPA owners that we never want to expire.
BLACKLISTED_PPAS = """
adobe-isv
chelsea-team
dennis-team
elvis-team
fluendo-isv
natick-team
netbook-remix-team
netbook-team
oem-solutions-group
payson
transyl
ubuntu-mobile
wheelbarrow
bzr
bzr-beta-ppa
bzr-nightly-ppa
""".split()

# Particular PPAs (not owners, unlike the whitelist) that should be
# expired even if they're private.
WHITELISTED_PPAS = """
landscape/lds-trunk
kubuntu-ninjas/ppa
""".split()


class ArchiveExpirer(LaunchpadCronScript):
    """Helper class for expiring old PPA binaries.

    Any PPA binary older than 30 days that is superseded or deleted
    will be marked for immediate expiry.
    """
    blacklist = BLACKLISTED_PPAS
    whitelist = WHITELISTED_PPAS

    def add_my_options(self):
        """Add script command line options."""
        self.parser.add_option(
            "-n", "--dry-run", action="store_true",
            dest="dryrun", metavar="DRY_RUN", default=False,
            help="If set, no transactions are committed")
        self.parser.add_option(
            "-e", "--expire-after", action="store", type="int",
            dest="num_days", metavar="DAYS", default=15,
            help=("The number of days after which to expire binaries. "
                  "Must be specified."))

    def determineSourceExpirables(self, num_days):
        """Return expirable libraryfilealias IDs."""
        stay_of_execution = '%d days' % num_days
        archive_types = (ArchivePurpose.PPA, ArchivePurpose.PARTNER)

        # The subquery here has to repeat the checks for privacy and
        # blacklisting on *other* publications that are also done in
        # the main loop for the archive being considered.
        results = self.store.execute("""
            SELECT lfa.id
            FROM
                LibraryFileAlias AS lfa,
                Archive,
                SourcePackageReleaseFile AS sprf,
                SourcePackageRelease AS spr,
                SourcePackagePublishingHistory AS spph
            WHERE
                lfa.id = sprf.libraryfile
                AND spr.id = sprf.sourcepackagerelease
                AND spph.sourcepackagerelease = spr.id
                AND spph.dateremoved < (
                    CURRENT_TIMESTAMP AT TIME ZONE 'UTC' - interval %s)
                AND spph.archive = archive.id
                AND archive.purpose IN %s
                AND lfa.expires IS NULL
            EXCEPT
            SELECT sprf.libraryfile
            FROM
                SourcePackageRelease AS spr,
                SourcePackageReleaseFile AS sprf,
                SourcePackagePublishingHistory AS spph,
                Archive AS a,
                Person AS p
            WHERE
                spr.id = sprf.sourcepackagerelease
                AND spph.sourcepackagerelease = spr.id
                AND spph.archive = a.id
                AND p.id = a.owner
                AND (
                    (p.name IN %s AND a.purpose = %s)
                    OR (a.private IS TRUE
                        AND (p.name || '/' || a.name) NOT IN %s)
                    OR a.purpose NOT IN %s
                    OR dateremoved >
                        CURRENT_TIMESTAMP AT TIME ZONE 'UTC' - interval %s
                    OR dateremoved IS NULL);
            """ % sqlvalues(
                stay_of_execution, archive_types, self.blacklist,
                ArchivePurpose.PPA, self.whitelist, archive_types,
                stay_of_execution))

        lfa_ids = results.get_all()
        return lfa_ids

    def determineBinaryExpirables(self, num_days):
        """Return expirable libraryfilealias IDs."""
        stay_of_execution = '%d days' % num_days
        archive_types = (ArchivePurpose.PPA, ArchivePurpose.PARTNER)

        # The subquery here has to repeat the checks for privacy and
        # blacklisting on *other* publications that are also done in
        # the main loop for the archive being considered.
        results = self.store.execute("""
            SELECT lfa.id
            FROM
                LibraryFileAlias AS lfa,
                Archive,
                BinaryPackageFile AS bpf,
                BinaryPackageRelease AS bpr,
                BinaryPackagePublishingHistory AS bpph
            WHERE
                lfa.id = bpf.libraryfile
                AND bpr.id = bpf.binarypackagerelease
                AND bpph.binarypackagerelease = bpr.id
                AND bpph.dateremoved < (
                    CURRENT_TIMESTAMP AT TIME ZONE 'UTC' -
                    interval %(stay_of_execution)s)
                AND bpph.archive = archive.id
                AND archive.purpose IN %(archive_types)s
                AND lfa.expires IS NULL
            EXCEPT
            SELECT bpf.libraryfile
            FROM
                BinaryPackageRelease AS bpr,
                BinaryPackageFile AS bpf,
                BinaryPackagePublishingHistory AS bpph,
                Archive AS a,
                Person AS p
            WHERE
                bpr.id = bpf.binarypackagerelease
                AND bpph.binarypackagerelease = bpr.id
                AND bpph.archive = a.id
                AND p.id = a.owner
                AND (
                    (p.name IN %(blacklist)s AND a.purpose = %(ppa)s)
                    OR (a.private IS TRUE
                        AND (p.name || '/' || a.name) NOT IN %(whitelist)s)
                    OR a.purpose NOT IN %(archive_types)s
                    OR dateremoved > (
                        CURRENT_TIMESTAMP AT TIME ZONE 'UTC' -
                        interval %(stay_of_execution)s)
                    OR dateremoved IS NULL)
            """ % sqlvalues(
                stay_of_execution=stay_of_execution,
                archive_types=archive_types,
                blacklist=self.blacklist,
                whitelist=self.whitelist,
                ppa=ArchivePurpose.PPA))

        lfa_ids = results.get_all()
        return lfa_ids

    def main(self):
        self.logger.info('Starting the PPA binary expiration')
        num_days = self.options.num_days
        self.logger.info("Expiring files up to %d days ago" % num_days)

        self.store = IStore(Archive)

        lfa_ids = self.determineSourceExpirables(num_days)
        lfa_ids.extend(self.determineBinaryExpirables(num_days))
        batch_count = 0
        batch_limit = 500
        for id in lfa_ids:
            self.logger.info("Expiring libraryfilealias %s" % id)
            self.store.execute("""
                UPDATE libraryfilealias
                SET expires = CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
                WHERE id = %s
                """ % id)
            batch_count += 1
            if batch_count % batch_limit == 0:
                if self.options.dryrun:
                    self.logger.info(
                        "%s done, not committing (dryrun mode)" % batch_count)
                    self.txn.abort()
                else:
                    self.logger.info(
                        "%s done, committing transaction" % batch_count)
                    self.txn.commit()

        if self.options.dryrun:
            self.txn.abort()
        else:
            self.txn.commit()

        self.logger.info('Finished PPA binary expiration')
