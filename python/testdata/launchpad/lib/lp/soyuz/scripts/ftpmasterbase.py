# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""FTPMaster base classes.

PackageLocation and SoyuzScript.
"""

__metaclass__ = type

__all__ = [
    'SoyuzScriptError',
    'SoyuzScript',
    ]

from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )
from lp.soyuz.adapters.packagelocation import build_package_location
from lp.soyuz.enums import ArchivePurpose


class SoyuzScriptError(Exception):
    """Raised when a soyuz script failed.

    The textual content should explain the error.
    """


class SoyuzScript(LaunchpadScript):
    """`LaunchpadScript` extended for Soyuz related use.

    Possible exceptions raised are:

     * `PackageLocationError`: specified package or distro does not exist
     * `LaunchpadScriptError`: only raised if entering via main(), ie this
        code is running as a genuine script.  In this case, this is
        also the _only_ exception to be raised.

    The test harness doesn't enter via main(), it calls mainTask(), so
    it does not see LaunchpadScriptError.

    Each script can extend:

     * `usage`: string describing the expected command-line format;
     * `description`: string describing the tool;
     * `success_message`: string to be presented on successful runs;
     * `mainTask`: a method to actually perform a specific task.

    See `add_my_options` for the default `SoyuzScript` command-line options.
    """
    location = None
    success_message = "Done."

    def add_my_options(self):
        """Adds SoyuzScript default options.

        Any subclass may override this method and call the add_*_options
        individually to reduce the number of available options as necessary.
        """
        self.add_transaction_options()
        self.add_distro_options()
        self.add_package_location_options()
        self.add_archive_options()

    def add_transaction_options(self):
        """Add SoyuzScript transaction-related options."""
        self.parser.add_option(
            '-n', '--dry-run', dest='dryrun', default=False,
            action='store_true', help='Do not commit changes.')

        self.parser.add_option(
            '-y', '--confirm-all', dest='confirm_all',
            default=False, action='store_true',
            help='Do not prompt the user for confirmation.')

    def add_distro_options(self):
        """Add SoyuzScript distro-related options."""
        self.parser.add_option(
            '-d', '--distribution', dest='distribution_name',
            default='ubuntu', action='store',
            help='Distribution name.')

        self.parser.add_option(
            '-s', '--suite', dest='suite', default=None,
            action='store', help='Suite name.')

    def add_package_location_options(self):
        """Add SoyuzScript package location-related options."""
        self.parser.add_option(
            "-c", "--component", dest="component", default=None,
            help="Component name.")

    def add_archive_options(self):
        """Add SoyuzScript archive-related options."""
        self.parser.add_option(
            '-p', '--ppa', dest='archive_owner_name', action='store',
            help='Archive owner name in case of PPA operations')

        self.parser.add_option(
            '--ppa-name', dest='archive_name', action='store', default="ppa",
            help='PPA name in case of PPA operations')

        self.parser.add_option(
            '-j', '--partner', dest='partner_archive', default=False,
            action='store_true',
            help='Specify partner archive')

    def _getUserConfirmation(self, full_question=None, valid_answers=None):
        """Use raw_input to collect user feedback.

        Return True if the user typed the first value of the given
        'valid_answers' (defaults to 'yes') or False otherwise.
        """
        if valid_answers is None:
            valid_answers = ['yes', 'no']
        display_answers = '[%s]' % (', '.join(valid_answers))

        if full_question is None:
            full_question = 'Confirm this transaction? %s ' % display_answers
        else:
            full_question = '%s %s' % (full_question, display_answers)

        answer = None
        while answer not in valid_answers:
            answer = raw_input(full_question)

        return answer == valid_answers[0]

    def waitForUserConfirmation(self):
        """Blocks the script flow waiting for a user confirmation.

        Return True immediately if options.confirm_all was passed or after
        getting a valid confirmation, False otherwise.
        """
        if not self.options.confirm_all and not self._getUserConfirmation():
            return False
        return True

    def setupLocation(self):
        """Setup `PackageLocation` for context distribution and suite."""
        # These can raise PackageLocationError, but we're happy to pass
        # it upwards.
        if getattr(self.options, 'partner_archive', ''):
            self.location = build_package_location(
                self.options.distribution_name,
                self.options.suite,
                ArchivePurpose.PARTNER)
        elif getattr(self.options, 'archive_owner_name', ''):
            self.location = build_package_location(
                self.options.distribution_name,
                self.options.suite,
                ArchivePurpose.PPA,
                self.options.archive_owner_name,
                self.options.archive_name)
        else:
            self.location = build_package_location(
                self.options.distribution_name,
                self.options.suite)

    def finishProcedure(self):
        """Script finalization procedure.

        'dry-run' command-line option will case the transaction to be
        immediatelly aborted.

        In normal mode it will ask for user confirmation (see
        `waitForUserConfirmation`) and will commit the transaction or abort
        it according to the user answer.

        Returns True if the transaction was committed, False otherwise.
        """
        if self.options.dryrun:
            self.logger.info('Dry run, so nothing to commit.')
            self.txn.abort()
            return False

        confirmed = self.waitForUserConfirmation()

        if confirmed:
            self.txn.commit()
            self.logger.info('Transaction committed.')
            self.logger.info(self.success_message)
            return True
        else:
            self.logger.info("Ok, see you later")
            self.txn.abort()
            return False

    def main(self):
        """LaunchpadScript entry point.

        Can only raise LaunchpadScriptFailure - other exceptions are
        absorbed into that.
        """
        try:
            self.setupLocation()
            self.mainTask()
        except SoyuzScriptError as err:
            raise LaunchpadScriptFailure(err)

        self.finishProcedure()

    def mainTask(self):
        """Main task to be performed by the script"""
        raise NotImplementedError
