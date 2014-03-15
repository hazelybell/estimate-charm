# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database classes for the CodeImportResult table."""

__metaclass__ = type
__all__ = ['CodeImportResult', 'CodeImportResultSet']

from sqlobject import (
    ForeignKey,
    StringCol,
    )
from zope.interface import implements

from lp.code.enums import CodeImportResultStatus
from lp.code.interfaces.codeimportresult import (
    ICodeImportResult,
    ICodeImportResultSet,
    )
from lp.registry.interfaces.person import validate_public_person
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase


class CodeImportResult(SQLBase):
    """See `ICodeImportResult`."""

    implements(ICodeImportResult)

    date_created = UtcDateTimeCol(notNull=True, default=UTC_NOW)

    code_import = ForeignKey(
        dbName='code_import', foreignKey='CodeImport', notNull=True)

    machine = ForeignKey(
        dbName='machine', foreignKey='CodeImportMachine', notNull=True)

    requesting_user = ForeignKey(
        dbName='requesting_user', foreignKey='Person',
        storm_validator=validate_public_person, default=None)

    log_excerpt = StringCol(default=None)

    log_file = ForeignKey(
        dbName='log_file', foreignKey='LibraryFileAlias', default=None)

    status = EnumCol(
        enum=CodeImportResultStatus, notNull=True)

    date_job_started = UtcDateTimeCol(notNull=True)

    @property
    def date_job_finished(self):
        """See `ICodeImportResult`."""
        return self.date_created

    @property
    def job_duration(self):
        return self.date_job_finished - self.date_job_started


class CodeImportResultSet(object):
    """See `ICodeImportResultSet`."""

    implements(ICodeImportResultSet)

    def new(self, code_import, machine, requesting_user, log_excerpt,
            log_file, status, date_job_started, date_job_finished=None):
        """See `ICodeImportResultSet`."""
        if date_job_finished is None:
            date_job_finished = UTC_NOW
        return CodeImportResult(
            code_import=code_import, machine=machine,
            requesting_user=requesting_user, log_excerpt=log_excerpt,
            log_file=log_file, status=status,
            date_job_started=date_job_started, date_created=date_job_finished)
