# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface for build farm job behaviors."""

__metaclass__ = type

__all__ = [
    'IBuildFarmJobBehavior',
    ]

from zope.interface import Interface


class IBuildFarmJobBehavior(Interface):

    def setBuilder(builder, slave):
        """Sets the associated builder and slave for this instance."""

    def logStartBuild(logger):
        """Log the start of a specific build queue item.

        The form of the log message will vary depending on the type of build.
        :param build_queue_item: A BuildQueueItem to build.
        :param logger: A logger to be used to log diagnostic information.
        """

    def dispatchBuildToSlave(build_queue_item_id, logger):
        """Dispatch a specific build to the slave.

        :param build_queue_item_id: An identifier for the build queue item.
        :param logger: A logger to be used to log diagnostic information.
        """

    def verifyBuildRequest(logger):
        """Carry out any pre-build checks.

        :param logger: A logger to be used to log diagnostic information.
        """

    def getBuildCookie():
        """Return a string which uniquely identifies the job."""

    def updateSlaveStatus(status_sentence, status_dict):
        """Update the slave status dict with custom values for this behavior.

        :param status_sentence: The value returned by the build slave's
           status() method.
        :param status_dict: A dict of the processed slave status values
           provided by all types: builder_status, build_id, and optionally
           build_status or logtail. This should have any behaviour-specific
           values added to it.
        """

    def handleStatus(bq, status, status_dict):
        """Update the build from a WAITING slave result.

        :param bq: The `BuildQueue` currently being processed.
        :param status: The tail of the BuildStatus (eg. OK or PACKAGEFAIL).
        :param status_dict: Slave status dict from
           `BuilderInteractor.slaveStatus` and `updateSlaveStatus`.
        """
