# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from lp.services.database.postgresql import ConnectionString
from lp.testing import TestCase


class TestConnectionString(TestCase):

    def test_relevant_fields_parsed(self):
        s = ('dbname=dbname user=user host=host port=port '
             'connect_timeout=timeout sslmode=mode')
        cs = ConnectionString(s)
        self.assertEqual('dbname', cs.dbname)
        self.assertEqual('user', cs.user)
        self.assertEqual('host', cs.host)
        self.assertEqual('port', cs.port)
        self.assertEqual('timeout', cs.connect_timeout)
        self.assertEqual('mode', cs.sslmode)

        # and check that str/repr have the same keys and values.
        self.assertContentEqual(s.split(), str(cs).split())
        self.assertContentEqual(s.split(), repr(cs).split())

    def test_hyphens_in_values(self):
        cs = ConnectionString('user=foo-bar host=foo.bar-baz.quux')
        self.assertEqual('foo-bar', cs.user)
        self.assertEqual('foo.bar-baz.quux', cs.host)

    def test_str_with_changes(self):
        initial = 'dbname=foo host=bar'
        expected = 'dbname=foo user=baz host=blah'
        cs = ConnectionString(initial)
        cs.host = 'blah'
        cs.user = 'baz'
        self.assertEqual(expected, str(cs))

    def test_rejects_quoted_strings(self):
        self.assertRaises(
            AssertionError, ConnectionString, "dbname='quoted string'")
