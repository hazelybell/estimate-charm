# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'RetryDepwaitTunableLoop',
    ]


import transaction

from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.database.bulk import load_related
from lp.services.database.interfaces import IStore
from lp.services.looptuner import (
    LoopTuner,
    TunableLoop,
    )
from lp.soyuz.interfaces.binarypackagebuild import UnparsableDependencies
from lp.soyuz.model.binarypackagebuild import BinaryPackageBuild
from lp.soyuz.model.distroarchseries import PocketChroot
from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease


class RetryDepwaitTunableLoop(TunableLoop):

    # We don't write too much, and it's important that we're timely.
    # Ignore the replication lag and long transaction checks by using a
    # basic LoopTuner.
    tuner_class = LoopTuner

    maximum_chunk_size = 5000

    def __init__(self, log, dry_run, abort_time=None):
        super(RetryDepwaitTunableLoop, self).__init__(log, abort_time)
        self.dry_run = dry_run
        self.start_at = 1
        self.store = IStore(BinaryPackageBuild)

    def findBuilds(self):
        return self.store.find(
            BinaryPackageBuild,
            BinaryPackageBuild.id >= self.start_at,
            BinaryPackageBuild.status == BuildStatus.MANUALDEPWAIT,
            ).order_by(BinaryPackageBuild.id)

    def isDone(self):
        return self.findBuilds().is_empty()

    def __call__(self, chunk_size):
        bpbs = list(self.findBuilds()[:chunk_size])
        sprs = load_related(
            SourcePackageRelease, bpbs, ['source_package_release_id'])
        load_related(SourcePackageName, sprs, ['sourcepackagenameID'])
        chroots = IStore(PocketChroot).find(
            PocketChroot,
            PocketChroot.distroarchseriesID.is_in(
                b.distro_arch_series_id for b in bpbs),
            PocketChroot.chroot != None)
        chroot_series = set(chroot.distroarchseriesID for chroot in chroots)
        for build in bpbs:
            if (build.distro_arch_series.distroseries.status ==
                    SeriesStatus.OBSOLETE
                or not build.can_be_retried
                or build.distro_arch_series_id not in chroot_series):
                continue
            try:
                build.updateDependencies()
            except UnparsableDependencies as e:
                self.log.error(e)
                continue

            if not build.dependencies:
                self.log.debug('Retrying %s', build.title)
                build.retry()
                build.buildqueue_record.score()

        self.start_at = bpbs[-1].id + 1

        if not self.dry_run:
            transaction.commit()
        else:
            transaction.abort()
