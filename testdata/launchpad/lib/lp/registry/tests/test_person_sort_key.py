# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the person_sort_key stored procedure and its in-app twin."""

__metaclass__ = type

from lp.registry.model.person import person_sort_key
from lp.testing import TestCase
from lp.testing.layers import DatabaseLayer


class TestPersonSortKeyBase:

    def test_composition(self):
        # person_sort_key returns the concatenation of the display name and
        # the name for use in sorting.
        self.assertSortKeysEqual(
            u"Stuart Bishop", u"stub",
            u"stuart bishop, stub")

    def test_whitespace(self):
        # Leading and trailing whitespace is removed.
        self.assertSortKeysEqual(
            u" Stuart Bishop\t", u"stub",
            u"stuart bishop, stub")

    def test_valid_name_is_assumed(self):
        # 'name' is assumed to be lowercase and not containing anything we
        # don't want. This should never happen as the valid_name database
        # constraint should prevent it.
        self.assertSortKeysEqual(
            u"Stuart Bishop", u" stub42!!!",
            u"stuart bishop,  stub42!!!")

    def test_strip_all_but_letters_and_whitespace(self):
        # Everything except for letters and whitespace is stripped.
        self.assertSortKeysEqual(
            u"-= Mass1v3 T0SSA =-", u"tossa",
            u"massv tssa, tossa")

    def test_non_ascii_allowed(self):
        # Non ASCII letters are currently allowed. Eventually they should
        # become transliterated to ASCII but we don't do this yet.
        self.assertSortKeysEqual(
            u"Bj\N{LATIN SMALL LETTER O WITH DIAERESIS}rn", "bjorn",
            u"bj\xf6rn, bjorn")

    def test_unicode_case_conversion(self):
        # Case conversion is handled correctly using Unicode.
        self.assertSortKeysEqual(
            u"Bj\N{LATIN CAPITAL LETTER O WITH DIAERESIS}rn", "bjorn",
            u"bj\xf6rn, bjorn") # Lower case o with diaeresis


class TestPersonSortKeyInDatabase(TestPersonSortKeyBase, TestCase):

    layer = DatabaseLayer

    def setUp(self):
        super(TestPersonSortKeyInDatabase, self).setUp()
        self.con = self.layer.connect()
        self.cur = self.con.cursor()

    def tearDown(self):
        super(TestPersonSortKeyInDatabase, self).tearDown()
        self.con.close()

    def get_person_sort_key(self, displayname, name):
        '''Calls the `person_sort_key` stored procedure.

        Note that although the stored procedure returns a UTF-8 encoded
        string, our database driver converts that to Unicode for us.
        '''
        # Note that as we are testing a PostgreSQL stored procedure, we should
        # pass it UTF-8 encoded strings to match our database encoding.
        self.cur.execute(
            "SELECT person_sort_key(%s, %s)", (
                displayname.encode("UTF-8"), name.encode("UTF-8")))
        return self.cur.fetchone()[0]

    def assertSortKeysEqual(self, displayname, name, expected):
        # The sort key from the database matches the expected sort key.
        self.assertEqual(
            expected, self.get_person_sort_key(
                displayname, name))


class PersonNames:
    """A fake with enough information for `person_sort_key`."""

    def __init__(self, displayname, name):
        self.displayname = displayname
        self.name = name


class TestPersonSortKeyInProcess(TestPersonSortKeyBase, TestCase):

    def assertSortKeysEqual(self, displayname, name, expected):
        # The sort key calculated in-process matches the expected sort key.
        self.assertEqual(
            expected, person_sort_key(
                PersonNames(displayname, name)))
