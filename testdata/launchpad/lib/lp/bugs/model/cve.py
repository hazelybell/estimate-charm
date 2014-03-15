# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'Cve',
    'CveSet',
    ]

import re

# SQL imports
from sqlobject import (
    SQLMultipleJoin,
    SQLObjectNotFound,
    SQLRelatedJoin,
    StringCol,
    )
from storm.expr import In
from storm.store import Store
# Zope
from zope.interface import implements

from lp.app.validators.cve import valid_cve
from lp.bugs.interfaces.buglink import IBugLinkTarget
from lp.bugs.interfaces.cve import (
    CveStatus,
    ICve,
    ICveSet,
    )
from lp.bugs.model.bug import Bug
from lp.bugs.model.bugcve import BugCve
from lp.bugs.model.buglinktarget import BugLinkTargetMixin
from lp.bugs.model.cvereference import CveReference
from lp.services.database.bulk import load_related
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase
from lp.services.database.stormexpr import fti_search


cverefpat = re.compile(r'(CVE|CAN)-((19|20)\d{2}\-\d{4})')


class Cve(SQLBase, BugLinkTargetMixin):
    """A CVE database record."""

    implements(ICve, IBugLinkTarget)

    _table = 'Cve'

    sequence = StringCol(notNull=True, alternateID=True)
    status = EnumCol(dbName='status', schema=CveStatus, notNull=True)
    description = StringCol(notNull=True)
    datecreated = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    datemodified = UtcDateTimeCol(notNull=True, default=UTC_NOW)

    # joins
    bugs = SQLRelatedJoin('Bug', intermediateTable='BugCve',
        joinColumn='cve', otherColumn='bug', orderBy='id')
    bug_links = SQLMultipleJoin('BugCve', joinColumn='cve', orderBy='id')
    references = SQLMultipleJoin(
        'CveReference', joinColumn='cve', orderBy='id')

    @property
    def url(self):
        """See ICve."""
        return ('http://www.cve.mitre.org/cgi-bin/cvename.cgi?name=%s'
                % self.sequence)

    @property
    def displayname(self):
        return 'CVE-%s' % self.sequence

    @property
    def title(self):
        return 'CVE-%s (%s)' % (self.sequence, self.status.title)

    # CveReference's
    def createReference(self, source, content, url=None):
        """See ICveReference."""
        return CveReference(cve=self, source=source, content=content,
            url=url)

    def removeReference(self, ref):
        assert ref.cve == self
        CveReference.delete(ref.id)

    # Template methods for BugLinkTargetMixin
    buglinkClass = BugCve

    def createBugLink(self, bug):
        """See BugLinkTargetMixin."""
        return BugCve(cve=self, bug=bug)


class CveSet:
    """The full set of ICve's."""

    implements(ICveSet)
    table = Cve

    def __init__(self, bug=None):
        """See ICveSet."""
        self.title = 'The Common Vulnerabilities and Exposures database'

    def __getitem__(self, sequence):
        """See ICveSet."""
        if sequence[:4] in ['CVE-', 'CAN-']:
            sequence = sequence[4:]
        if not valid_cve(sequence):
            return None
        try:
            return Cve.bySequence(sequence)
        except SQLObjectNotFound:
            return None

    def getAll(self):
        """See ICveSet."""
        return Cve.select(orderBy="-datemodified")

    def __iter__(self):
        """See ICveSet."""
        return iter(Cve.select())

    def new(self, sequence, description, status=CveStatus.CANDIDATE):
        """See ICveSet."""
        return Cve(sequence=sequence, status=status,
            description=description)

    def latest(self, quantity=5):
        """See ICveSet."""
        return Cve.select(orderBy='-datecreated', limit=quantity)

    def latest_modified(self, quantity=5):
        """See ICveSet."""
        return Cve.select(orderBy='-datemodified', limit=quantity)

    def search(self, text):
        """See ICveSet."""
        return Cve.select(
            fti_search(Cve, text), distinct=True, orderBy='-datemodified')

    def inText(self, text):
        """See ICveSet."""
        # let's look for matching entries
        cves = set()
        for match in cverefpat.finditer(text):
            # let's get the core CVE data
            sequence = match.group(2)
            # see if there is already a matching CVE ref in the db, and if
            # not, then create it
            cve = self[sequence]
            if cve is None:
                cve = Cve(sequence=sequence, status=CveStatus.DEPRECATED,
                    description="This CVE was automatically created from "
                    "a reference found in an email or other text. If you "
                    "are reading this, then this CVE entry is probably "
                    "erroneous, since this text should be replaced by "
                    "the official CVE description automatically.")
            cves.add(cve)

        return sorted(cves, key=lambda a: a.sequence)

    def inMessage(self, message):
        """See ICveSet."""
        cves = set()
        for messagechunk in message:
            if messagechunk.blob is not None:
                # we don't process attachments
                continue
            elif messagechunk.content is not None:
                # look for potential CVE URL's and create them as needed
                cves.update(self.inText(messagechunk.content))
            else:
                raise AssertionError('MessageChunk without content or blob.')
        return sorted(cves, key=lambda a: a.sequence)

    def getBugCvesForBugTasks(self, bugtasks, cve_mapper=None):
        """See ICveSet."""
        bugs = load_related(Bug, bugtasks, ('bugID', ))
        if len(bugs) == 0:
            return []
        bug_ids = [bug.id for bug in bugs]

        # Do not use BugCve instances: Storm may need a very long time
        # to look up the bugs and CVEs referenced by a BugCve instance
        # when the +cve view of a distroseries is rendered: There may
        # be a few thousand (bug, CVE) tuples, while the number of bugs
        # and CVEs is in the order of hundred. It is much more efficient
        # to retrieve just (bug_id, cve_id) from the BugCve table and
        # to map this to (Bug, CVE) here, instead of letting Storm
        # look up the CVE and bug for a BugCve instance, even if bugs
        # and CVEs are bulk loaded.
        store = Store.of(bugtasks[0])
        bugcve_ids = store.find(
            (BugCve.bugID, BugCve.cveID), In(BugCve.bugID, bug_ids))
        bugcve_ids.order_by(BugCve.bugID, BugCve.cveID)
        bugcve_ids = list(bugcve_ids)

        cve_ids = set(cve_id for bug_id, cve_id in bugcve_ids)
        cves = store.find(Cve, In(Cve.id, list(cve_ids)))

        if cve_mapper is None:
            cvemap = dict((cve.id, cve) for cve in cves)
        else:
            cvemap = dict((cve.id, cve_mapper(cve)) for cve in cves)
        bugmap = dict((bug.id, bug) for bug in bugs)
        return [
            (bugmap[bug_id], cvemap[cve_id])
            for bug_id, cve_id in bugcve_ids
            ]

    def getBugCveCount(self):
        """See ICveSet."""
        return BugCve.select().count()
