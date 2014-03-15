# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import cStringIO
from datetime import datetime
import email
import os
import re
import subprocess


class Bug:
    def __init__(self, db, id, package=None, date=None, status=None,
                 originator=None, severity=None, tags=None, report=None):
        self.db = db
        self.id = id
        self._emails = []

        if package:
            self.package = package
        if date:
            self.date = date
        if status:
            self.status = status
        if originator:
            self.originator = originator
        if severity:
            self.severity = severity
        if tags:
            self.tags = tags
        if report:
            self.report = report
        description = None

    def is_open(self):
        #return not self.done and 'fixed' not in self.tags
        return self.status != 'done' and 'fixed' not in self.tags

    def affects_unstable(self):
        return 'sid' in self.tags or ('woody' not in self.tags and
                                 'sarge' not in self.tags and
                                 'experimental' not in self.tags)

    def affects_package(self, packageset):
        for package in self.packagelist():
            if package in packageset:
                return True
        return False

    def is_release_critical(self):
        return self.severity in ('critical', 'grave', 'serious')

    def __str__(self):
        return 'Bug#%d' % self.id

    def __getattr__(self, name):
        # Lazy loading of non-indexed attributes

        if not self.db.load(self, name):
            raise AttributeError, name

        if not hasattr(self, name):
            raise InternalError, "Database.load did not provide attribute '%s'" % name

        return getattr(self, name)

    def packagelist(self):
        if self.package is None:
            return []
        if ',' in self.package:
            return self.package.split(',')
        return [self.package]

    def emails(self):
        if self._emails:
            return self._emails
        for comment in self.comments:
            message = email.message_from_string(comment)
            self._emails.append(message)
        return self._emails

class IndexParseError(Exception): pass
class StatusParseError(Exception): pass
class StatusMissing(Exception): pass
class SummaryMissing(Exception): pass
class SummaryParseError(Exception): pass
class SummaryVersionError(Exception): pass
class ReportMissing(Exception): pass
class ReportParseError(Exception): pass
class LogMissing(Exception): pass
class LogParseFailed(Exception): pass
class InternalError(Exception): pass

class Database:
    def __init__(self, root, debbugs_pl, subdir='db-h'):
        self.root = root
        self.debbugs_pl = debbugs_pl
        self.subdir = subdir

    class bug_iterator:
        index_record = re.compile(r'^(?P<package>\S+) (?P<bugid>\d+) (?P<date>\d+) (?P<status>\w+) \[(?P<originator>.*)\] (?P<severity>\w+)(?: (?P<tags>.*))?$')

        def __init__(self, db, filter=None):
            self.db = db
            self.index = open(os.path.join(self.db.root, 'index/index.db'))
            self.filter = filter

        def next(self):
            line = self.index.readline()
            if not line:
                raise StopIteration

            match = self.index_record.match(line)
            if not match:
                raise IndexParseError(line)

            return Bug(self.db,
                       int(match.group('bugid')),
                       match.group('package'),
                       datetime.fromtimestamp(int(match.group('date'))),
                       match.group('status'),
                       match.group('originator'),
                       match.group('severity'),
                       match.group('tags').split(' '))

    def load(self, bug, name):
        if name in ('originator', 'date', 'subject', 'msgid', 'package',
                    'tags', 'done', 'forwarded', 'mergedwith', 'severity'):
            self.load_summary(bug)
        elif name in ('report', 'description'):
            self.load_report(bug)
        elif name in ('comments',):
            self.load_log(bug)
        elif name == 'status':
            if bug.done is not None:
                bug.status = 'done'
            elif bug.forwarded is not None:
                bug.status = 'forwarded'
            else:
                bug.status = 'open'
        else:
            return False

        return True

    def load_summary(self, bug):
        summary = os.path.join(self.root, self.subdir, self._hash(bug),
                               '%d.summary' % bug.id)

        try:
            fd = open(summary)
        except IOError as e:
            if e.errno == 2:
                raise SummaryMissing, summary
            raise

        try:
            message = email.message_from_file(fd)
        except Exception as e:
            raise SummaryParseError, '%s: %s' % (summary, str(e))

        version = message['format-version']
        if version is None:
            raise SummaryParseError, "%s: Missing Format-Version" % summary

        if version not in ('2', '3'):
            raise SummaryVersionError, "%s: I don't understand version %s" % (summary, version)

        bug.originator = message['submitter']
        bug.date = datetime.fromtimestamp(int(message['date']))
        bug.subject = message['subject']
        bug.msgid = message['message-id']
        bug.package = message['package']
        bug.done = message['done']
        bug.forwarded = message['forwarded-to']
        bug.severity = message['severity']

        if 'merged-with' in message:
            bug.mergedwith = map(int,message['merged-with'].split(' '))
        else:
            bug.mergedwith = []

        if 'tags' in message:
            bug.tags = message['tags'].split(' ')
        else:
            bug.tags = []

    def load_report(self, bug):
        report = os.path.join(self.root, 'db-h', self._hash(bug), '%d.report' % bug.id)

        try:
            fd = open(report)
        except IOError as e:
            if e.errno == 2:
                raise ReportMissing, report
            raise

        bug.report = fd.read()
        fd.close()

        report_msg = email.message_from_string(bug.report)
        charset = report_msg.get_content_charset('ascii')
        description = report_msg.get_payload(decode=True)
        bug.description = description.decode(charset)

    def load_log(self, bug):
        log = os.path.join(self.root, self.subdir, self._hash(bug),
            '%d.log' % bug.id)
        comments = []

        # We set the perl path manually so that debbugs-log.pl can
        # always find the Debbugs::Log module.
        debbugs_path = os.path.dirname(self.debbugs_pl)
        command = ['perl', '-I', debbugs_path, self.debbugs_pl, log]

        try:
            process = subprocess.Popen(command,
                stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                stderr=subprocess.PIPE)
            logreader = process.stdout
            comment = cStringIO.StringIO()
            for line in logreader:
                if line == '.\n':
                    comments.append(comment.getvalue())
                    comment = cStringIO.StringIO()
                elif line.startswith('.'):
                    comment.write(line[1:])
                else:
                    comment.write(line)
            logreader.close()

            if comment.tell() != 0:
                raise LogParseFailed(
                    'Unterminated comment from debbugs-log.pl')

            process.wait()
            err = process.stderr
            errors = "\n".join(err.readlines())
            if process.returncode != 0:
                raise LogParseFailed(errors)

        except IOError as e:
            if e.errno == 2:
                raise LogMissing, log
            raise

        bug.comments = comments

    def _hash(self, bug):
        return '%02d' % (bug.id % 100)

    def __iter__(self):
        return self.bug_iterator(self, None)

    def __getitem__(self, bug_id):
        bug = Bug(self, bug_id)
        try:
            self.load_summary(bug)
        except SummaryMissing:
            raise KeyError(bug_id)
        return bug

if __name__ == '__main__':
    import sys

    for bug in Database('/srv/debzilla.no-name-yet.com/debbugs'):
        try:
            print bug, bug.subject
        except Exception as e:
            print >>sys.stderr, '%s: %s' % (e.__class__.__name__, str(e))


