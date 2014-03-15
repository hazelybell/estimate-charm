# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Librarian garbage collection tests"""

__metaclass__ = type

from cStringIO import StringIO
from datetime import timedelta
import os
import shutil
from subprocess import (
    PIPE,
    Popen,
    STDOUT,
    )
import sys
import tempfile

from sqlobject import SQLObjectNotFound
import transaction

from lp.services.config import config
from lp.services.database.sqlbase import (
    connect,
    cursor,
    ISOLATION_LEVEL_AUTOCOMMIT,
    )
from lp.services.librarian.client import LibrarianClient
from lp.services.librarian.model import (
    LibraryFileAlias,
    LibraryFileContent,
    )
from lp.services.librarianserver import librariangc
from lp.services.log.logger import BufferLogger
from lp.services.utils import utc_now
from lp.testing import TestCase
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer


class TestLibrarianGarbageCollection(TestCase):
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestLibrarianGarbageCollection, self).setUp()
        self.client = LibrarianClient()
        self.patch(librariangc, 'log', BufferLogger())

        # A value we use in a number of tests. This represents the
        # stay of execution hard coded into the garbage collector.
        # We don't destroy any data unless it has been waiting to be
        # destroyed for longer than this period. We pick a value
        # that is close enough to the stay of execution so that
        # forgetting timezone information will break things, but
        # far enough so that how long it takes the test to run
        # is not an issue. 'stay_of_excution - 1 hour' fits these
        # criteria.
        self.recent_past = utc_now() - timedelta(days=6, hours=23)
        # A time beyond the stay of execution.
        self.ancient_past = utc_now() - timedelta(days=30)

        self.f1_id, self.f2_id = self._makeDupes()

        switch_dbuser(config.librarian_gc.dbuser)
        self.ztm = self.layer.txn

        # Make sure the files exist. We do this in setup, because we
        # need to use the get_file_path method later in the setup and we
        # want to be sure it is working correctly.
        path = librariangc.get_file_path(self.f1_id)
        self.failUnless(os.path.exists(path), "Librarian uploads failed")

        # Make sure that every file the database knows about exists on disk.
        # We manually remove them for tests that need to cope with missing
        # library items.
        self.ztm.begin()
        cur = cursor()
        cur.execute("SELECT id FROM LibraryFileContent")
        for content_id in (row[0] for row in cur.fetchall()):
            path = librariangc.get_file_path(content_id)
            if not os.path.exists(path):
                if not os.path.exists(os.path.dirname(path)):
                    os.makedirs(os.path.dirname(path))
                open(path, 'w').write('whatever')
        self.ztm.abort()

        self.con = connect(
            user=config.librarian_gc.dbuser,
            isolation=ISOLATION_LEVEL_AUTOCOMMIT)

    def tearDown(self):
        self.con.rollback()
        self.con.close()
        del self.con
        super(TestLibrarianGarbageCollection, self).tearDown()

    def _makeDupes(self):
        """Create two duplicate LibraryFileContent entries with one
        LibraryFileAlias each. Return the two LibraryFileAlias ids as a
        tuple.
        """
        # Connect to the database as a user with file upload privileges,
        # in this case the PostgreSQL default user who happens to be an
        # administrator on launchpad development boxes.
        switch_dbuser('testadmin')
        ztm = self.layer.txn

        ztm.begin()
        # Add some duplicate files
        content = 'This is some content'
        f1_id = self.client.addFile(
                'foo.txt', len(content), StringIO(content), 'text/plain',
                )
        f1 = LibraryFileAlias.get(f1_id)
        f2_id = self.client.addFile(
                'foo.txt', len(content), StringIO(content), 'text/plain',
                )
        f2 = LibraryFileAlias.get(f2_id)

        # Make sure the duplicates really are distinct
        self.failIfEqual(f1_id, f2_id)
        self.failIfEqual(f1.contentID, f2.contentID)

        f1.date_created = self.ancient_past
        f2.date_created = self.ancient_past
        f1.content.datecreated = self.ancient_past
        f2.content.datecreated = self.ancient_past

        del f1, f2

        ztm.commit()

        return f1_id, f2_id

    def test_MergeDuplicates(self):
        # Merge the duplicates
        librariangc.merge_duplicates(self.con)

        # merge_duplicates should have committed
        self.ztm.begin()
        self.ztm.abort()

        # Confirm that the duplicates have been merged
        self.ztm.begin()
        f1 = LibraryFileAlias.get(self.f1_id)
        f2 = LibraryFileAlias.get(self.f2_id)
        self.failUnlessEqual(f1.contentID, f2.contentID)

    def test_DeleteUnreferencedAliases(self):
        self.ztm.begin()

        # Confirm that our sample files are there.
        f1 = LibraryFileAlias.get(self.f1_id)
        f2 = LibraryFileAlias.get(self.f2_id)
        # Grab the content IDs related to these
        # unreferenced LibraryFileAliases
        c1_id = f1.contentID
        c2_id = f2.contentID
        del f1, f2
        self.ztm.abort()

        # Delete unreferenced aliases
        librariangc.delete_unreferenced_aliases(self.con)

        # This should have committed
        self.ztm.begin()

        # Confirm that the LibaryFileContents are still there.
        LibraryFileContent.get(c1_id)
        LibraryFileContent.get(c2_id)

        # But the LibraryFileAliases should be gone
        self.assertRaises(SQLObjectNotFound, LibraryFileAlias.get, self.f1_id)
        self.assertRaises(SQLObjectNotFound, LibraryFileAlias.get, self.f2_id)

    def test_DeleteUnreferencedAliases2(self):
        # Don't delete LibraryFileAliases accessed recently

        # Merge the duplicates. Both our aliases now point to the same
        # LibraryFileContent
        librariangc.merge_duplicates(self.con)

        # We now have two aliases sharing the same content.
        self.ztm.begin()
        f1 = LibraryFileAlias.get(self.f1_id)
        f2 = LibraryFileAlias.get(self.f2_id)
        self.assertEqual(f1.content, f2.content)

        # Flag one of our LibraryFileAliases as being recently created
        f1.date_created = self.recent_past

        del f1
        del f2
        self.ztm.commit()

        # Delete unreferenced LibraryFileAliases. This should remove
        # the alias with the ID self.f2_id, but the other should stay,
        # as it was accessed recently.
        librariangc.delete_unreferenced_aliases(self.con)

        self.ztm.begin()
        LibraryFileAlias.get(self.f1_id)
        self.assertRaises(SQLObjectNotFound, LibraryFileAlias.get, self.f2_id)

    def test_DeleteUnreferencedAndWellExpiredAliases(self):
        # LibraryFileAliases can be removed after they have expired

        # Merge the duplicates. Both our aliases now point to the same
        # LibraryFileContent
        librariangc.merge_duplicates(self.con)

        # Flag one of our LibraryFileAliases with an expiry date in the past
        self.ztm.begin()
        f1 = LibraryFileAlias.get(self.f1_id)
        f1.expires = self.ancient_past
        del f1
        self.ztm.commit()

        # Delete unreferenced LibraryFileAliases. This should remove our
        # example aliases, as one is unreferenced with a NULL expiry and
        # the other is unreferenced with an expiry in the past.
        librariangc.delete_unreferenced_aliases(self.con)

        # Make sure both our example files are gone
        self.ztm.begin()
        self.assertRaises(SQLObjectNotFound, LibraryFileAlias.get, self.f1_id)
        self.assertRaises(SQLObjectNotFound, LibraryFileAlias.get, self.f2_id)

    def test_DoneDeleteUnreferencedButNotExpiredAliases(self):
        # LibraryFileAliases can be removed only after they have expired.
        # If an explicit expiry is set and in recent past (currently up to
        # one week ago), the files hang around.

        # Merge the duplicates. Both our aliases now point to the same
        # LibraryFileContent
        librariangc.merge_duplicates(self.con)

        # Flag one of our LibraryFileAliases with an expiry date in the
        # recent past.
        self.ztm.begin()
        f1 = LibraryFileAlias.get(self.f1_id)
        f1.expires = self.recent_past
        del f1
        self.ztm.commit()

        # Delete unreferenced LibraryFileAliases. This should not remove our
        # example aliases, as one is unreferenced with a NULL expiry and
        # the other is unreferenced with an expiry in the recent past.
        librariangc.delete_unreferenced_aliases(self.con)

        # Make sure both our example files are still there
        self.ztm.begin()
        # Our recently expired LibraryFileAlias is still available.
        LibraryFileAlias.get(self.f1_id)

    def test_deleteWellExpiredAliases(self):
        # LibraryFileAlias records that are expired are unlinked from their
        # content.

        # Flag one of our LibraryFileAliases with an expiry date in the past
        self.ztm.begin()
        f1 = LibraryFileAlias.get(self.f1_id)
        f1.expires = self.ancient_past
        del f1
        self.ztm.commit()

        # Unlink expired LibraryFileAliases.
        librariangc.expire_aliases(self.con)

        self.ztm.begin()
        # Make sure the well expired f1 is still there, but has no content.
        f1 = LibraryFileAlias.get(self.f1_id)
        self.assert_(f1.content is None)
        # f2 should still have content, as it isn't flagged for expiry.
        f2 = LibraryFileAlias.get(self.f2_id)
        self.assert_(f2.content is not None)

    def test_ignoreRecentlyExpiredAliases(self):
        # LibraryFileAlias records that have expired recently are not
        # garbage collected.

        # Flag one of our LibraryFileAliases with an expiry date in the
        # recent past.
        self.ztm.begin()
        f1 = LibraryFileAlias.get(self.f1_id)
        f1.expires = self.recent_past  # Within stay of execution.
        del f1
        self.ztm.commit()

        # Unlink expired LibraryFileAliases.
        librariangc.expire_aliases(self.con)

        self.ztm.begin()
        # Make sure f1 is still there and has content. This ensures that
        # our stay of execution is still working.
        f1 = LibraryFileAlias.get(self.f1_id)
        self.assert_(f1.content is not None)
        # f2 should still have content, as it isn't flagged for expiry.
        f2 = LibraryFileAlias.get(self.f2_id)
        self.assert_(f2.content is not None)

    def test_DeleteUnreferencedContent(self):
        # Merge the duplicates. This creates an
        # unreferenced LibraryFileContent
        librariangc.merge_duplicates(self.con)

        self.ztm.begin()

        # Locate the unreferenced LibraryFileContent
        cur = cursor()
        cur.execute("""
            SELECT LibraryFileContent.id
            FROM LibraryFileContent
            LEFT OUTER JOIN LibraryFileAlias
                ON LibraryFileContent.id = LibraryFileAlias.content
            WHERE LibraryFileAlias.id IS NULL
                AND LibraryFileContent.id IN (%d, %d)
            """ % (self.f1_id, self.f2_id))
        results = cur.fetchall()
        self.failUnlessEqual(len(results), 1)
        unreferenced_id = results[0][0]

        self.ztm.abort()

        # Make sure the file exists on disk
        path = librariangc.get_file_path(unreferenced_id)
        self.failUnless(os.path.exists(path))

        # Delete unreferenced content
        librariangc.delete_unreferenced_content(self.con)

        # Make sure the file is gone
        self.failIf(os.path.exists(path))

        # delete_unreferenced_content should have committed
        self.ztm.begin()

        # Make sure the unreferenced entries have all gone
        cur = cursor()
        cur.execute("""
            SELECT LibraryFileContent.id
            FROM LibraryFileContent
            LEFT OUTER JOIN LibraryFileAlias
                ON LibraryFileContent.id = LibraryFileAlias.content
            WHERE LibraryFileAlias.id IS NULL
            """)
        results = list(cur.fetchall())
        self.failUnlessEqual(
                len(results), 0, 'Too many results %r' % (results,)
                )

    def test_DeleteUnreferencedContent2(self):
        # Like testDeleteUnreferencedContent, except that the file is
        # removed from disk before attempting to remove the unreferenced
        # LibraryFileContent.
        #
        # Because the garbage collector will remove an unreferenced file from
        # disk before it commits the database changes, it is possible that the
        # db removal will fail (eg. an exception was raised on COMMIT) leaving
        # the rows untouched in the database but no file on disk.
        # This is fine, as the next gc run will attempt it again and
        # nothing can use unreferenced files anyway. This test ensures
        # that this all works.

        # Merge the duplicates. This creates an
        # unreferenced LibraryFileContent
        librariangc.merge_duplicates(self.con)

        self.ztm.begin()

        # Locate the unreferenced LibraryFileContent
        cur = cursor()
        cur.execute("""
            SELECT LibraryFileContent.id
            FROM LibraryFileContent
            LEFT OUTER JOIN LibraryFileAlias
                ON LibraryFileContent.id = LibraryFileAlias.content
            WHERE LibraryFileAlias.id IS NULL
                AND LibraryFileContent.id IN (%d, %d)
            """ % (self.f1_id, self.f2_id))
        results = cur.fetchall()
        self.failUnlessEqual(len(results), 1)
        unreferenced_id = results[0][0]

        self.ztm.abort()

        # Make sure the file exists on disk
        path = librariangc.get_file_path(unreferenced_id)
        self.failUnless(os.path.exists(path))

        # Remove the file from disk
        os.unlink(path)
        self.failIf(os.path.exists(path))

        # Delete unreferenced content
        librariangc.delete_unreferenced_content(self.con)

        # Make sure the file is gone
        self.failIf(os.path.exists(path))

        # delete_unreferenced_content should have committed
        self.ztm.begin()

        # Make sure the unreferenced entries have all gone
        cur = cursor()
        cur.execute("""
            SELECT LibraryFileContent.id
            FROM LibraryFileContent
            LEFT OUTER JOIN LibraryFileAlias
                ON LibraryFileContent.id = LibraryFileAlias.content
            WHERE LibraryFileAlias.id IS NULL
            """)
        results = list(cur.fetchall())
        self.failUnlessEqual(
                len(results), 0, 'Too many results %r' % (results,)
                )

    def test_deleteUnwantedFiles(self):
        self.ztm.begin()
        cur = cursor()

        # We may find files in the LibraryFileContent repository
        # that do not have an corresponding LibraryFileContent row.

        # Find a content_id we can easily delete and do so. This row is
        # removed from the database, leaving an orphaned file on the
        # filesystem that should be removed.
        cur.execute("""
            SELECT LibraryFileContent.id
            FROM LibraryFileContent
            LEFT OUTER JOIN LibraryFileAlias
                ON LibraryFileContent.id = content
            WHERE LibraryFileAlias.id IS NULL
            LIMIT 1
            """)
        content_id = cur.fetchone()[0]
        cur.execute("""
                DELETE FROM LibraryFileContent WHERE id=%s
                """, (content_id,))
        self.ztm.commit()

        path = librariangc.get_file_path(content_id)
        self.failUnless(os.path.exists(path))

        # Ensure delete_unreferenced_files does not remove the file, because
        # it will have just been created (has a recent date_created). There
        # is a window between file creation and the garbage collector
        # bothering to remove the file to avoid the race condition where the
        # garbage collector is run whilst a file is being uploaded.
        librariangc.delete_unwanted_files(self.con)
        self.failUnless(os.path.exists(path))

        # To test removal does occur when we want it to, we need to trick
        # the garbage collector into thinking it is tomorrow.
        org_time = librariangc.time

        def tomorrow_time():
            return org_time() + 24 * 60 * 60 + 1

        try:
            librariangc.time = tomorrow_time
            librariangc.delete_unwanted_files(self.con)
        finally:
            librariangc.time = org_time

        self.failIf(os.path.exists(path))

        # Make sure nothing else has been removed from disk
        self.ztm.begin()
        cur = cursor()
        cur.execute("""
                SELECT id FROM LibraryFileContent
                """)
        for content_id in (row[0] for row in cur.fetchall()):
            path = librariangc.get_file_path(content_id)
            self.failUnless(os.path.exists(path))

    def test_deleteUnwantedFilesIgnoresNoise(self):
        # Directories with invalid names in the storage area are
        # ignored. They are reported as warnings though.

        # Not a hexidecimal number.
        noisedir1_path = os.path.join(config.librarian_server.root, 'zz')

        # Too long
        noisedir2_path = os.path.join(config.librarian_server.root, '111')

        # Long non-hexadecimal number
        noisedir3_path = os.path.join(config.librarian_server.root, '11.bak')

        try:
            os.mkdir(noisedir1_path)
            os.mkdir(noisedir2_path)
            os.mkdir(noisedir3_path)

            # Files in the noise directories.
            noisefile1_path = os.path.join(noisedir1_path, 'abc')
            noisefile2_path = os.path.join(noisedir2_path, 'def')
            noisefile3_path = os.path.join(noisedir2_path, 'ghi')
            open(noisefile1_path, 'w').write('hello')
            open(noisefile2_path, 'w').write('there')
            open(noisefile3_path, 'w').write('testsuite')

            # Pretend it is tomorrow to ensure the files don't count as
            # recently created, and run the delete_unwanted_files process.
            org_time = librariangc.time

            def tomorrow_time():
                return org_time() + 24 * 60 * 60 + 1

            try:
                librariangc.time = tomorrow_time
                librariangc.delete_unwanted_files(self.con)
            finally:
                librariangc.time = org_time

            # None of the rubbish we created has been touched.
            self.assert_(os.path.isdir(noisedir1_path))
            self.assert_(os.path.isdir(noisedir2_path))
            self.assert_(os.path.isdir(noisedir3_path))
            self.assert_(os.path.exists(noisefile1_path))
            self.assert_(os.path.exists(noisefile2_path))
            self.assert_(os.path.exists(noisefile3_path))
        finally:
            # We need to clean this up ourselves, as the standard librarian
            # cleanup only removes files it knows where valid to avoid
            # accidents.
            shutil.rmtree(noisedir1_path)
            shutil.rmtree(noisedir2_path)
            shutil.rmtree(noisedir3_path)

        # Can't check the ordering, so we'll just check that one of the
        # warnings are there.
        self.assertIn(
            "WARNING Ignoring invalid directory zz",
            librariangc.log.getLogBuffer())

    def test_delete_unwanted_files_bug437084(self):
        # There was a bug where delete_unwanted_files() would die
        # if the last file found on disk was unwanted.
        switch_dbuser('testadmin')
        content = 'foo'
        self.client.addFile(
            'foo.txt', len(content), StringIO(content), 'text/plain')
        # Roll back the database changes, leaving the file on disk.
        transaction.abort()

        switch_dbuser(config.librarian_gc.dbuser)

        # This should cope.
        librariangc.delete_unwanted_files(self.con)

    def test_delete_unwanted_files_follows_symlinks(self):
        # In production, our tree has symlinks in it now.  We need to be able
        # to cope.
        # First, let's make sure we have some trash.
        switch_dbuser('testadmin')
        content = 'foo'
        self.client.addFile(
            'foo.txt', len(content), StringIO(content), 'text/plain')
        # Roll back the database changes, leaving the file on disk.
        transaction.abort()

        switch_dbuser(config.librarian_gc.dbuser)

        # Now, we will move the directory containing the trash somewhere else
        # and make a symlink to it.
        original = os.path.join(config.librarian_server.root, '00', '00')
        newdir = tempfile.mkdtemp()
        alt = os.path.join(newdir, '00')
        shutil.move(original, alt)
        os.symlink(alt, original)

        # Now we will do our thing.  This is the actual test.  It used to
        # fail.
        librariangc.delete_unwanted_files(self.con)

        # Clean up.
        os.remove(original)
        shutil.move(alt, original)
        shutil.rmtree(newdir)

    def test_cronscript(self):
        script_path = os.path.join(
                config.root, 'cronscripts', 'librarian-gc.py'
                )
        cmd = [sys.executable, script_path, '-q']
        process = Popen(cmd, stdout=PIPE, stderr=STDOUT, stdin=PIPE)
        (script_output, _empty) = process.communicate()
        self.failUnlessEqual(
            process.returncode, 0, 'Error: %s' % script_output)
        self.failUnlessEqual(script_output, '')

        # Make sure that our example files have been garbage collected
        self.ztm.begin()
        self.assertRaises(SQLObjectNotFound, LibraryFileAlias.get, self.f1_id)
        self.assertRaises(SQLObjectNotFound, LibraryFileAlias.get, self.f2_id)

        # And make sure stuff that *is* referenced remains
        LibraryFileAlias.get(2)
        cur = cursor()
        cur.execute("SELECT count(*) FROM LibraryFileAlias")
        count = cur.fetchone()[0]
        self.failIfEqual(count, 0)
        cur.execute("SELECT count(*) FROM LibraryFileContent")
        count = cur.fetchone()[0]
        self.failIfEqual(count, 0)

    def test_confirm_no_clock_skew(self):
        # There should not be any clock skew when running the test suite.
        librariangc.confirm_no_clock_skew(self.con)

        # To test this function raises an excption when it should,
        # the garbage collector into thinking it is tomorrow.
        org_time = librariangc.time

        def tomorrow_time():
            return org_time() + 24 * 60 * 60 + 1

        try:
            librariangc.time = tomorrow_time
            self.assertRaises(
                Exception, librariangc.confirm_no_clock_skew, (self.con,)
                )
        finally:
            librariangc.time = org_time


class TestBlobCollection(TestCase):
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestBlobCollection, self).setUp()
        # Add in some sample data
        cur = cursor()

        # First a blob that has been unclaimed and expired.
        cur.execute("""
            INSERT INTO LibraryFileContent (filesize, sha1, md5, sha256)
            VALUES (666, 'whatever', 'whatever', 'whatever')
            """)
        cur.execute("""SELECT currval('libraryfilecontent_id_seq')""")
        self.expired_lfc_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO LibraryFileAlias (
                content, filename, mimetype, expires)
            VALUES (
                %s, 'whatever', 'whatever',
                CURRENT_TIMESTAMP - '1 day'::interval
                )
            """, (self.expired_lfc_id,))
        cur.execute("""SELECT currval('libraryfilealias_id_seq')""")
        self.expired_lfa_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO TemporaryBlobStorage (uuid, file_alias)
            VALUES ('uuid', %s)
            """, (self.expired_lfa_id,))
        cur.execute("""SELECT currval('temporaryblobstorage_id_seq')""")
        self.expired_blob_id = cur.fetchone()[0]

        # Add ApportJob and Job entries - these need to be removed
        # too.
        cur.execute("""
            INSERT INTO Job (status, date_finished)
            VALUES (0, CURRENT_TIMESTAMP - interval '2 days') RETURNING id
            """)
        self.expired_job_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO ApportJob (job, blob, job_type)
            VALUES (%s, %s, 0) RETURNING id
            """, (self.expired_job_id, self.expired_blob_id))
        self.expired_apportjob_id = cur.fetchone()[0]

        # Next a blob that has expired, but claimed and now linked to
        # elsewhere in the database
        cur.execute("""
            INSERT INTO LibraryFileContent (filesize, sha1, md5, sha256)
            VALUES (666, 'whatever', 'whatever', 'whatever')
            """)
        cur.execute("""SELECT currval('libraryfilecontent_id_seq')""")
        self.expired2_lfc_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO LibraryFileAlias (
                content, filename, mimetype, expires)
            VALUES (
                %s, 'whatever', 'whatever',
                CURRENT_TIMESTAMP - '1 day'::interval
                )
            """, (self.expired2_lfc_id,))
        cur.execute("""SELECT currval('libraryfilealias_id_seq')""")
        self.expired2_lfa_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO TemporaryBlobStorage (uuid, file_alias)
            VALUES ('uuid2', %s)
            """, (self.expired2_lfa_id,))
        cur.execute("""SELECT currval('temporaryblobstorage_id_seq')""")
        self.expired2_blob_id = cur.fetchone()[0]

        # Link it somewhere else, unexpired
        cur.execute("""
            INSERT INTO LibraryFileAlias (content, filename, mimetype)
            VALUES (%s, 'whatever', 'whatever')
            """, (self.expired2_lfc_id,))
        cur.execute("""
            UPDATE Person SET mugshot=currval('libraryfilealias_id_seq')
            WHERE name='stub'
            """)

        # And a non expired blob
        cur.execute("""
            INSERT INTO LibraryFileContent (filesize, sha1, md5, sha256)
            VALUES (666, 'whatever', 'whatever', 'whatever')
            """)
        cur.execute("""SELECT currval('libraryfilecontent_id_seq')""")
        self.unexpired_lfc_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO LibraryFileAlias (
                content, filename, mimetype, expires)
            VALUES (
                %s, 'whatever', 'whatever',
                CURRENT_TIMESTAMP + '1 day'::interval
                )
            """, (self.unexpired_lfc_id,))
        cur.execute("""SELECT currval('libraryfilealias_id_seq')""")
        self.unexpired_lfa_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO TemporaryBlobStorage (uuid, file_alias)
            VALUES ('uuid3', %s)
            """, (self.unexpired_lfa_id,))
        cur.execute("""SELECT currval('temporaryblobstorage_id_seq')""")
        self.unexpired_blob_id = cur.fetchone()[0]
        self.layer.txn.commit()

        # Make sure all the librarian files actually exist on disk
        cur = cursor()
        cur.execute("SELECT id FROM LibraryFileContent")
        for content_id in (row[0] for row in cur.fetchall()):
            path = librariangc.get_file_path(content_id)
            if not os.path.exists(path):
                if not os.path.exists(os.path.dirname(path)):
                    os.makedirs(os.path.dirname(path))
                open(path, 'w').write('whatever')
        self.layer.txn.abort()

        switch_dbuser(config.librarian_gc.dbuser)

        # Open a connection for our test
        self.con = connect(
            user=config.librarian_gc.dbuser,
            isolation=ISOLATION_LEVEL_AUTOCOMMIT)

        self.patch(librariangc, 'log', BufferLogger())

    def tearDown(self):
        self.con.rollback()
        self.con.close()
        super(TestBlobCollection, self).tearDown()

    def test_DeleteExpiredBlobs(self):
        # Delete expired blobs from the TemporaryBlobStorage table
        librariangc.delete_expired_blobs(self.con)

        cur = self.con.cursor()

        # Our expired blob should be gone
        cur.execute("""
            SELECT * FROM TemporaryBlobStorage WHERE id=%s
            """, (self.expired_blob_id,)
            )
        self.failUnless(cur.fetchone() is None)

        # As should our expired blob linked elsewhere.
        cur.execute("""
            SELECT * FROM TemporaryBlobStorage WHERE id=%s
            """, (self.expired2_blob_id,)
            )
        self.failUnless(cur.fetchone() is None)

        # But our unexpired blob is still hanging around.
        cur.execute("""
            SELECT * FROM TemporaryBlobStorage WHERE id=%s
            """, (self.unexpired_blob_id,)
            )
        self.failUnless(cur.fetchone() is not None)

        # Now delete our unreferenced aliases and unreferenced content
        cur.execute(
                "SELECT id FROM LibraryFileAlias WHERE id IN (%s, %s, %s)",
                (self.expired_lfa_id, self.expired2_lfa_id,
                    self.unexpired_lfa_id))
        librariangc.delete_unreferenced_aliases(self.con)
        librariangc.delete_unreferenced_content(self.con)
        cur.execute(
                "SELECT id FROM LibraryFileAlias WHERE id IN (%s, %s, %s)",
                (self.expired_lfa_id, self.expired2_lfa_id,
                    self.unexpired_lfa_id))

        # The first expired blob should now be entirely gone
        cur.execute("""
            SELECT * FROM LibraryFileAlias WHERE id=%s
            """, (self.expired_lfa_id,))
        self.failUnless(cur.fetchone() is None)
        cur.execute("""
            SELECT * FROM LibraryFileContent WHERE id=%s
            """, (self.expired_lfc_id,))
        self.failUnless(cur.fetchone() is None)

        # The second expired blob will has lost its LibraryFileAlias,
        # but the content is still hanging around because something else
        # linked to it.
        cur.execute("""
            SELECT * FROM LibraryFileAlias WHERE id=%s
            """, (self.expired2_lfa_id,))
        self.failUnless(cur.fetchone() is None)
        cur.execute("""
            SELECT * FROM LibraryFileContent WHERE id=%s
            """, (self.expired2_lfc_id,))
        self.failUnless(cur.fetchone() is not None)

        # The unexpired blob should be unaffected
        cur.execute("""
            SELECT * FROM LibraryFileAlias WHERE id=%s
            """, (self.unexpired_lfa_id,))
        self.failUnless(cur.fetchone() is not None)
        cur.execute("""
            SELECT * FROM LibraryFileContent WHERE id=%s
            """, (self.unexpired_lfc_id,))
        self.failUnless(cur.fetchone() is not None)

    def test_cronscript(self):
        # Run the cronscript
        script_path = os.path.join(
                config.root, 'cronscripts', 'librarian-gc.py'
                )
        cmd = [sys.executable, script_path, '-q']
        process = Popen(cmd, stdout=PIPE, stderr=STDOUT, stdin=PIPE)
        (script_output, _empty) = process.communicate()
        self.failUnlessEqual(
            process.returncode, 0, 'Error: %s' % script_output)
        self.failUnlessEqual(script_output, '')

        cur = self.con.cursor()

        # Make sure that our blobs have been garbage collectd
        cur.execute("SELECT count(*) FROM TemporaryBlobStorage")
        count = cur.fetchone()[0]
        self.failUnlessEqual(count, 1)

        cur.execute("""
            SELECT count(*) FROM LibraryFileAlias
            WHERE id IN (%s, %s, %s)
            """, (
                self.expired_lfa_id,
                self.expired2_lfa_id,
                self.unexpired_lfa_id
                ))
        count = cur.fetchone()[0]
        self.failUnlessEqual(count, 1)

        cur.execute("""
            SELECT count(*) FROM LibraryFileContent
            WHERE id IN (%s, %s, %s)
            """, (
                self.expired_lfc_id,
                self.expired2_lfc_id,
                self.unexpired_lfc_id
                ))
        count = cur.fetchone()[0]
        self.failIfEqual(count, 2)
