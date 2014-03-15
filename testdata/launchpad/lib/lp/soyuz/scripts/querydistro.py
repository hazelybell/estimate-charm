# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Distribution querying utility."""

__metaclass__ = type

__all__ = ['LpQueryDistro']

from lp.registry.interfaces.series import SeriesStatus
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )
from lp.soyuz.adapters.packagelocation import (
    build_package_location,
    PackageLocationError,
    )


class LpQueryDistro(LaunchpadScript):
    """Main class for scripts/ftpmaster-tools/lp-query-distro.py."""

    def __init__(self, *args, **kwargs):
        """Initialize dynamic 'usage' message and LaunchpadScript parent.

        Also initialize the list 'allowed_arguments'.
        """
        self.allowed_actions = ['supported']
        self.usage = '%%prog <%s>' % ' | '.join(self.allowed_actions)
        LaunchpadScript.__init__(self, *args, **kwargs)

    def add_my_options(self):
        """Add 'distribution' and 'suite' context options."""
        self.parser.add_option(
            '-d', '--distribution', dest='distribution_name',
            default='ubuntu', help='Context distribution name.')
        self.parser.add_option(
            '-s', '--suite', dest='suite', default=None,
            help='Context suite name.')

    def main(self):
        """Main procedure, basically a runAction wrapper.

        Execute the given and allowed action using the default presenter
        (see self.runAction for further information).
        """
        self.runAction()

    def _buildLocation(self):
        """Build a PackageLocation object

        The location will correspond to the given 'distribution' and 'suite',
        Any PackageLocationError occurring at this point will be masked into
        LaunchpadScriptFailure.
        """
        try:
            self.location = build_package_location(
                distribution_name=self.options.distribution_name,
                suite=self.options.suite)
        except PackageLocationError as err:
            raise LaunchpadScriptFailure(err)

    def defaultPresenter(self, result):
        """Default result presenter.

        Directly prints result in the standard output (print).
        """
        print result

    def runAction(self, presenter=None):
        """Run a given initialized action (self.action_name).

        It accepts an optional 'presenter' which will be used to
        store/present the action result.

        Ensure at least one argument was passed, known as 'action'.
        Verify if the given 'action' is listed as an 'allowed_action'.
        Raise LaunchpadScriptFailure if those requirements were not
        accomplished.

        It builds context 'location' object (see self._buildLocation).

        It may raise LaunchpadScriptFailure is the 'action' is not properly
        supported by the current code (missing corresponding property).
        """
        if presenter is None:
            presenter = self.defaultPresenter

        if len(self.args) != 1:
            raise LaunchpadScriptFailure('<action> is required')

        [self.action_name] = self.args

        if self.action_name not in self.allowed_actions:
            raise LaunchpadScriptFailure(
                'Action "%s" is not supported' % self.action_name)

        self._buildLocation()

        try:
            action_result = getattr(self, self.action_name)
        except AttributeError:
            raise AssertionError(
                "No handler found for action '%s'" % self.action_name)

        presenter(action_result)

    def checkNoSuiteDefined(self):
        """Raises LaunchpadScriptError if a suite location was passed.

        It is re-used in action properties to avoid conflicting contexts,
        i.e, passing an arbitrary 'suite' and asking for the CURRENT suite
        in the context distribution.
        """
        if self.options.suite is not None:
            raise LaunchpadScriptFailure(
                "Action does not accept defined suite.")

    @property
    def supported(self):
        """Return the names of the distroseries currently supported.

        'supported' means not EXPERIMENTAL or OBSOLETE.

        It is restricted for the context distribution.

        It may raise `LaunchpadScriptFailure` if a suite was passed on the
        command-line or if there is not supported distroseries for the
        distribution given.

        Return a space-separated list of distroseries names.
        """
        self.checkNoSuiteDefined()
        supported_series = []
        unsupported_status = (SeriesStatus.EXPERIMENTAL,
                              SeriesStatus.OBSOLETE)
        for distroseries in self.location.distribution:
            if distroseries.status not in unsupported_status:
                supported_series.append(distroseries.name)

        if not supported_series:
            raise LaunchpadScriptFailure(
                'There is no supported distroseries for %s' %
                self.location.distribution.name)

        return " ".join(supported_series)
