# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface classes for CodeImportResult, i.e. completed code import jobs."""

__metaclass__ = type
__all__ = [
    'ICodeImportResult',
    'ICodeImportResultSet',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Datetime,
    Int,
    Object,
    Text,
    )

from lp import _
from lp.code.enums import CodeImportResultStatus
from lp.code.interfaces.codeimport import ICodeImport
from lp.code.interfaces.codeimportmachine import ICodeImportMachine
from lp.registry.interfaces.person import IPerson
from lp.services.librarian.interfaces import ILibraryFileAlias


class ICodeImportResult(Interface):
    """A completed code import job."""

    id = Int(readonly=True, required=True)

    date_created = Datetime(readonly=True, required=True)

    code_import = Object(
        schema=ICodeImport, readonly=True, required=True,
        description=_("The code import for which the job was run."))

    machine = Object(
        schema=ICodeImportMachine, readonly=True, required=True,
        description=_("The machine the job ran on."))

    requesting_user = Object(
        schema=IPerson, readonly=True, required=False,
        description=_("The user that requested the import, if any."))

    log_excerpt = Text(
        readonly=True, required=False,
        description=_("The last few lines of the partial log, in case it "
                      "is set."))

    log_file = Object(
        schema=ILibraryFileAlias, readonly=True, required=False,
        description=_("A partial log of the job for users to see. It is "
                      "normally only recorded if the job failed in a step "
                      "that interacts with the remote repository. If a job "
                      "was successful, or failed in a houskeeping step, the "
                      "log file would not contain information useful to the "
                      "user."))

    status = Choice(
        vocabulary=CodeImportResultStatus, readonly=True, required=True,
        description=_("How the job ended. Success, some kind of failure, or "
                      "some kind of interruption before completion."))

    date_job_started = Datetime(
        readonly=True, required=True,
        description=_("When the job started running."))

    date_job_finished = Datetime(
        readonly=True, required=True,
        description=_("When the job stopped running."))

    job_duration = Attribute("How long did the job take to run.")


class ICodeImportResultSet(Interface):
    """The set of all CodeImportResults."""

    def new(code_import, machine, requesting_user, log_excerpt, log_file,
            status, date_job_started, date_job_finished=None):
        """Create a CodeImportResult with the given details.

        The date the job finished is assumed to be now and so is not
        passed in as a parameter.

        :param code_import: The code import for which the job was run.
        :param machine: The machine the job ran on.
        :param requesting_user: The user that requested the import, if any.
            If None, this means that the job was executed because it was
            automatically scheduled.
        :param log_excerpt: The last few lines of the log.
        :param log_file: A link to the log in the librarian.
        :param status: A status code from CodeImportResultStatus.
        :param date_job_started: The date the job started.
        :param date_job_finished: The date the job finished, defaults to now.
        """
