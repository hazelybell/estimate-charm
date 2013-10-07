# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Upload processor for Soyuz."""

__metaclass__ = type
__all__ = ['ProcessUpload']

import os

from lp.archiveuploader.uploadpolicy import findPolicyByName
from lp.archiveuploader.uploadprocessor import UploadProcessor
from lp.services.scripts.base import (
    LaunchpadCronScript,
    LaunchpadScriptFailure,
    )


class ProcessUpload(LaunchpadCronScript):
    """`LaunchpadScript` wrapper for `UploadProcessor`."""

    def add_my_options(self):
        self.parser.add_option(
            "-n", "--dry-run", action="store_true",
            dest="dryrun", metavar="DRY_RUN", default=False,
            help=("Whether to treat this as a dry-run or not."
                  "Also implies -KM."))

        self.parser.add_option(
            "-K", "--keep", action="store_true",
            dest="keep", metavar="KEEP", default=False,
            help="Whether to keep or not the uploads directory.")

        self.parser.add_option(
            "-M", "--no-mails", action="store_true",
            dest="nomails", default=False,
            help="Whether to suppress the sending of mails or not.")

        self.parser.add_option(
            "--builds", action="store_true",
            dest="builds", default=False,
            help="Whether to interpret leaf names as build ids.")

        self.parser.add_option(
            "-J", "--just-leaf", action="store", dest="leafname",
            default=None, help="A specific leaf dir to limit to.",
            metavar = "LEAF")

        self.parser.add_option(
            "-C", "--context", action="store", dest="context",
            metavar="CONTEXT", default="insecure",
            help="The context in which to consider the upload.")

        self.parser.add_option(
            "-d", "--distro", action="store", dest="distro", metavar="DISTRO",
            default="ubuntu", help="Distribution to give back from")

        self.parser.add_option(
            "-s", "--series", action="store", default=None,
            dest="distroseries", metavar="DISTROSERIES",
            help="Distro series to give back from.")

        self.parser.add_option(
            "-a", "--announce", action="store", dest="announcelist",
            metavar="ANNOUNCELIST", help="Override the announcement list")

    def main(self):
        if len(self.args) != 1:
            raise LaunchpadScriptFailure(
                "Need to be given exactly one non-option "
                "argument, namely the fsroot for the upload.")

        self.options.base_fsroot = os.path.abspath(self.args[0])

        if not os.path.isdir(self.options.base_fsroot):
            raise LaunchpadScriptFailure(
                "%s is not a directory" % self.options.base_fsroot)

        self.logger.debug("Initializing connection.")
        def getPolicy(distro, build):
            self.options.distro = distro.name
            policy = findPolicyByName(self.options.context)
            policy.setOptions(self.options)
            if self.options.builds:
                assert build, "--builds specified but no build"
                policy.distroseries = build.distro_series
                policy.pocket = build.pocket
                policy.archive = build.archive
            return policy
        processor = UploadProcessor(self.options.base_fsroot,
            self.options.dryrun, self.options.nomails, self.options.builds,
            self.options.keep, getPolicy, self.txn, self.logger)
        processor.processUploadQueue(self.options.leafname)

    @property
    def lockfilename(self):
        """Return specific lockfilename according to the policy used.

        Each different p-u policy requires and uses a different lockfile.
        This is because they are run by different users and are independent
        of each other.
        """
        return "process-upload-%s.lock" % self.options.context


