# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import datetime

from lazr.batchnavigator.interfaces import IRangeFactory
import pytz
import simplejson
from storm.expr import (
    compile,
    Desc,
    )
from storm.store import EmptyResultSet
from testtools.matchers import (
    LessThan,
    Not,
    )
from zope.security.proxy import isinstance as zope_isinstance

from lp.bugs.model.bugtask import BugTaskSet
from lp.registry.model.person import Person
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.librarian.model import LibraryFileAlias
from lp.services.webapp.batching import (
    BatchNavigator,
    DateTimeJSONEncoder,
    ShadowedList,
    StormRangeFactory,
    )
from lp.services.webapp.interfaces import StormRangeFactoryError
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import LaunchpadFunctionalLayer


class TestStormRangeFactory(TestCaseWithFactory):
    """Tests for StormRangeFactory."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestStormRangeFactory, self).setUp()
        self.error_messages = []

    def makeStormResultSet(self):
        bug = self.factory.makeBug()
        for count in range(5):
            person = self.factory.makePerson()
            with person_logged_in(person):
                bug.markUserAffected(person, True)
        return bug.users_affected

    def makeDecoratedStormResultSet(self):
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            for count in range(5):
                self.factory.makeBugAttachment(bug=bug, owner=bug.owner)
        result = bug.attachments
        self.assertTrue(zope_isinstance(result, DecoratedResultSet))
        return result

    def test_StormRangeFactory_implements_IRangeFactory(self):
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset)
        self.assertTrue(verifyObject(IRangeFactory, range_factory))

    def test_StormRangeFactory_needs__ordered_result_set(self):
        # If a result set is not ordered, it cannot be used with a
        # StormRangeFactory.
        resultset = self.makeStormResultSet()
        resultset.order_by()
        exception = self.assertRaises(
            StormRangeFactoryError, StormRangeFactory, resultset)
        self.assertEqual(
            "StormRangeFactory requires a sorted result set.",
            str(exception))

    def test_getOrderValuesFor__one_sort_column(self):
        # StormRangeFactory.getOrderValuesFor() returns the values
        # of the fields used in order_by expresssions for a given
        # result row.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.id)
        range_factory = StormRangeFactory(resultset)
        order_values = range_factory.getOrderValuesFor(resultset[0])
        self.assertEqual([resultset[0].id], order_values)

    def test_getOrderValuesFor__two_sort_columns(self):
        # Sorting by more than one column is supported.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.displayname, Person.name)
        range_factory = StormRangeFactory(resultset)
        order_values = range_factory.getOrderValuesFor(resultset[0])
        self.assertEqual(
            [resultset[0].displayname, resultset[0].name], order_values)

    def test_getOrderValuesFor__string_as_sort_expression(self):
        # Sorting by a string expression is not supported.
        resultset = self.makeStormResultSet()
        resultset.order_by('Person.id')
        range_factory = StormRangeFactory(resultset)
        exception = self.assertRaises(
            StormRangeFactoryError, range_factory.getOrderValuesFor,
            resultset[0])
        self.assertEqual(
            "StormRangeFactory only supports sorting by PropertyColumn, "
            "not by 'Person.id'.",
            str(exception))

    def test_getOrderValuesFor__generic_storm_expression_as_sort_expr(self):
        # Sorting by a generic Strom expression is not supported.
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset)
        exception = self.assertRaises(
            StormRangeFactoryError, range_factory.getOrderValuesFor,
            resultset[0])
        self.assertTrue(
            str(exception).startswith(
                'StormRangeFactory only supports sorting by PropertyColumn, '
                'not by <storm.expr.SQL object at'))

    def test_getOrderValuesFor__decorated_result_set(self):
        # getOrderValuesFor() knows how to retrieve SQL sort values
        # from DecoratedResultSets.
        resultset = self.makeDecoratedStormResultSet()
        range_factory = StormRangeFactory(resultset)
        self.assertEqual(
            [resultset[0].id], range_factory.getOrderValuesFor(resultset[0]))

    def test_getOrderValuesFor__value_from_second_element_of_result_row(self):
        # getOrderValuesFor() can retrieve values from attributes
        # of any Storm table class instance which appear in a result row.
        resultset = self.makeDecoratedStormResultSet()
        resultset = resultset.order_by(LibraryFileAlias.id)
        plain_resultset = resultset.get_plain_result_set()
        range_factory = StormRangeFactory(resultset)
        self.assertEqual(
            [plain_resultset[0][1].id],
            range_factory.getOrderValuesFor(plain_resultset[0]))

    def test_getOrderValuesFor__descending_sort_order(self):
        # getOrderValuesFor() can retrieve values from reverse sorted
        # columns.
        resultset = self.makeStormResultSet()
        resultset = resultset.order_by(Desc(Person.id))
        range_factory = StormRangeFactory(resultset)
        self.assertEqual(
            [resultset[0].id], range_factory.getOrderValuesFor(resultset[0]))

    def test_getOrderValuesFor__table_not_included_in_results(self):
        # Attempts to use a sort by a column which does not appear in the
        # data returned by the query raise a StormRangeFactoryError.
        resultset = self.makeStormResultSet()
        resultset.order_by(LibraryFileAlias.id)
        range_factory = StormRangeFactory(resultset)
        exception = self.assertRaises(
            StormRangeFactoryError, range_factory.getOrderValuesFor,
            resultset[0])
        self.assertEqual(
            "Instances of <class "
            "'lp.services.librarian.model.LibraryFileAlias'> are "
            "not contained in the result set, but are required to retrieve "
            "the value of LibraryFileAlias.id.",
            str(exception))

    def test_DatetimeJSONEncoder(self):
        # DateTimeJSONEncoder represents Python datetime objects as strings
        # where the value is represented in the ISO time format.
        self.assertEqual(
            '"2011-07-25T00:00:00"',
            simplejson.dumps(datetime(2011, 7, 25), cls=DateTimeJSONEncoder))

        # DateTimeJSONEncoder works for the regular Python types that can
        # represented as JSON strings.
        encoded = simplejson.dumps(
            ('foo', 1, 2.0, [3, 4], {5: 'bar'}, datetime(2011, 7, 24)),
            cls=DateTimeJSONEncoder)
        self.assertEqual(
            '["foo", 1, 2.0, [3, 4], {"5": "bar"}, "2011-07-24T00:00:00"]',
            encoded
            )

    def test_getEndpointMemos(self):
        # getEndpointMemos() returns JSON representations of the
        # sort fields of the first and last element of a batch.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.name)
        range_factory = StormRangeFactory(resultset)
        memo_value = range_factory.getOrderValuesFor(resultset[0])
        request = LaunchpadTestRequest(
            QUERY_STRING='memo=%s' % simplejson.dumps(memo_value))
        batchnav = BatchNavigator(
            resultset, request, size=3, range_factory=range_factory)
        first, last = range_factory.getEndpointMemos(batchnav.batch)
        expected_first = simplejson.dumps(
            [resultset[1].name], cls=DateTimeJSONEncoder)
        expected_last = simplejson.dumps(
            [resultset[3].name], cls=DateTimeJSONEncoder)
        self.assertEqual(expected_first, first)
        self.assertEqual(expected_last, last)

    def test_getEndpointMemos__decorated_result_set(self):
        # getEndpointMemos() works for DecoratedResultSet
        # instances too.
        resultset = self.makeDecoratedStormResultSet()
        resultset.order_by(LibraryFileAlias.id)
        range_factory = StormRangeFactory(resultset)
        request = LaunchpadTestRequest()
        batchnav = BatchNavigator(
            resultset, request, size=3, range_factory=range_factory)
        first, last = range_factory.getEndpointMemos(batchnav.batch)
        expected_first = simplejson.dumps(
            [resultset.get_plain_result_set()[0][1].id],
            cls=DateTimeJSONEncoder)
        expected_last = simplejson.dumps(
            [resultset.get_plain_result_set()[2][1].id],
            cls=DateTimeJSONEncoder)
        self.assertEqual(expected_first, first)
        self.assertEqual(expected_last, last)

    def logError(self, message):
        # An error callback for StormResultSet.
        self.error_messages.append(message)

    def test_parseMemo__empty_value(self):
        # parseMemo() returns None for an empty memo value.
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset, self.logError)
        self.assertIs(None, range_factory.parseMemo(''))
        self.assertEqual(0, len(self.error_messages))

    def test_parseMemo__json_error(self):
        # parseMemo() returns None for formally invalid JSON strings.
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset, self.logError)
        self.assertIs(None, range_factory.parseMemo('foo'))
        self.assertEqual(
            ['memo is not a valid JSON string.'], self.error_messages)

    def test_parseMemo__json_no_sequence(self):
        # parseMemo() accepts only JSON representations of lists.
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset, self.logError)
        self.assertIs(None, range_factory.parseMemo(simplejson.dumps(1)))
        self.assertEqual(
            ['memo must be the JSON representation of a list.'],
            self.error_messages)

    def test_parseMemo__wrong_list_length(self):
        # parseMemo() accepts only lists which have as many elements
        # as the number of sort expressions used in the SQL query of
        # the result set.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.name, Person.id)
        range_factory = StormRangeFactory(resultset, self.logError)
        self.assertIs(
            None, range_factory.parseMemo(simplejson.dumps([1])))
        expected_message = (
            'Invalid number of elements in memo string. Expected: 2, got: 1')
        self.assertEqual([expected_message], self.error_messages)

    def test_parseMemo__memo_type_check(self):
        # parseMemo() accepts only lists containing values that can
        # be used in sort expression of the given result set.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.datecreated, Person.name, Person.id)
        range_factory = StormRangeFactory(resultset, self.logError)
        invalid_memo = [datetime(2011, 7, 25, 11, 30, 30, 45), 'foo', 'bar']
        json_data = simplejson.dumps(invalid_memo, cls=DateTimeJSONEncoder)
        self.assertIs(None, range_factory.parseMemo(json_data))
        self.assertEqual(["Invalid parameter: 'bar'"], self.error_messages)

    def test_parseMemo__valid_data(self):
        # If a memo string contains valid data, parseMemo returns this data.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.datecreated, Person.name, Person.id)
        range_factory = StormRangeFactory(resultset, self.logError)
        valid_memo = [
            datetime(2011, 7, 25, 11, 30, 30, 45, tzinfo=pytz.UTC), 'foo', 1]
        json_data = simplejson.dumps(valid_memo, cls=DateTimeJSONEncoder)
        self.assertEqual(valid_memo, range_factory.parseMemo(json_data))
        self.assertEqual(0, len(self.error_messages))

    def test_parseMemo__short_iso_timestamp(self):
        # An ISO timestamp without fractions of a second
        # (YYYY-MM-DDThh:mm:ss) is a valid value for columns which
        # store datetime values.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.datecreated)
        range_factory = StormRangeFactory(resultset, self.logError)
        valid_short_timestamp_json = '["2011-07-25T11:30:30"]'
        self.assertEqual(
            [datetime(2011, 7, 25, 11, 30, 30, tzinfo=pytz.UTC)],
            range_factory.parseMemo(valid_short_timestamp_json))
        self.assertEqual(0, len(self.error_messages))

    def test_parseMemo__long_iso_timestamp(self):
        # An ISO timestamp with fractions of a second
        # (YYYY-MM-DDThh:mm:ss.ffffff) is a valid value for columns
        # which store datetime values.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.datecreated)
        range_factory = StormRangeFactory(resultset, self.logError)
        valid_long_timestamp_json = '["2011-07-25T11:30:30.123456"]'
        self.assertEqual(
            [datetime(2011, 7, 25, 11, 30, 30, 123456, tzinfo=pytz.UTC)],
            range_factory.parseMemo(valid_long_timestamp_json))
        self.assertEqual(0, len(self.error_messages))

    def test_parseMemo__short_iso_timestamp_with_tzoffset(self):
        # An ISO timestamp with fractions of a second and a time zone
        # offset (YYYY-MM-DDThh:mm:ss.ffffff+hh:mm) is a valid value
        # for columns which store datetime values.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.datecreated)
        range_factory = StormRangeFactory(resultset, self.logError)
        valid_long_timestamp_json = '["2011-07-25T11:30:30-01:00"]'
        self.assertEqual(
            [datetime(2011, 7, 25, 12, 30, 30, tzinfo=pytz.UTC)],
            range_factory.parseMemo(valid_long_timestamp_json))
        self.assertEqual(0, len(self.error_messages))

    def test_parseMemo__long_iso_timestamp_with_tzoffset(self):
        # An ISO timestamp with fractions of a second and a time zone
        # offset (YYYY-MM-DDThh:mm:ss.ffffff+hh:mm) is a valid value
        # for columns which store datetime values.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.datecreated)
        range_factory = StormRangeFactory(resultset, self.logError)
        valid_long_timestamp_json = '["2011-07-25T11:30:30.123456+01:00"]'
        self.assertEqual(
            [datetime(2011, 7, 25, 10, 30, 30, 123456, tzinfo=pytz.UTC)],
            range_factory.parseMemo(valid_long_timestamp_json))
        self.assertEqual(0, len(self.error_messages))

    def test_parseMemo__invalid_iso_timestamp_value(self):
        # An ISO timestamp with an invalid date is rejected as a memo
        # string.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.datecreated)
        range_factory = StormRangeFactory(resultset, self.logError)
        invalid_timestamp_json = '["2011-05-35T11:30:30"]'
        self.assertIs(
            None, range_factory.parseMemo(invalid_timestamp_json))
        self.assertEqual(
            ["Invalid datetime value: '2011-05-35T11:30:30'"],
            self.error_messages)

    def test_parseMemo__nonsensical_iso_timestamp_value(self):
        # A memo string is rejected when an ISO timespamp is expected
        # but a nonsensical string is provided.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.datecreated)
        range_factory = StormRangeFactory(resultset, self.logError)
        nonsensical_timestamp_json = '["bar"]'
        self.assertIs(
            None, range_factory.parseMemo(nonsensical_timestamp_json))
        self.assertEqual(
            ["Invalid datetime value: 'bar'"],
            self.error_messages)

    def test_parseMemo__descending_sort_order(self):
        # Validation of a memo string against a descending sort order works.
        resultset = self.makeStormResultSet()
        resultset.order_by(Desc(Person.id))
        range_factory = StormRangeFactory(resultset, self.logError)
        self.assertEqual(
            [1], range_factory.parseMemo(simplejson.dumps([1])))

    def test_reverseSortOrder(self):
        # reverseSortOrder() wraps a plain PropertyColumn instance into
        # Desc(), and it returns the plain PropertyCOlumn for a Desc()
        # expression.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.id, Desc(Person.name))
        range_factory = StormRangeFactory(resultset, self.logError)
        reverse_person_id, person_name = range_factory.reverseSortOrder()
        self.assertTrue(isinstance(reverse_person_id, Desc))
        self.assertIs(Person.id, reverse_person_id.expr)
        self.assertIs(Person.name, person_name)

    def test_limitsGroupedByOrderDirection(self):
        # limitsGroupedByOrderDirection() returns a sequence of
        # (expressions, memos), where expressions is a list of
        # ORDER BY expressions which either are all instances of
        # PropertyColumn, or are all instances of Desc(PropertyColumn).
        # memos are the related limit values.
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset, self.logError)
        order_by = [
            Person.id, Person.datecreated, Person.name, Person.displayname]
        limits = [1, datetime(2011, 07, 25, 0, 0, 0), 'foo', 'bar']
        result = range_factory.limitsGroupedByOrderDirection(order_by, limits)
        self.assertEqual([(order_by, limits)], result)
        order_by = [
            Desc(Person.id), Desc(Person.datecreated), Desc(Person.name),
            Desc(Person.displayname)]
        result = range_factory.limitsGroupedByOrderDirection(order_by, limits)
        self.assertEqual([(order_by, limits)], result)
        order_by = [
            Person.id, Person.datecreated, Desc(Person.name),
            Desc(Person.displayname)]
        result = range_factory.limitsGroupedByOrderDirection(order_by, limits)
        self.assertEqual(
            [(order_by[:2], limits[:2]), (order_by[2:], limits[2:])], result)

    def test_lessThanOrGreaterThanExpression__asc(self):
        # beforeOrAfterExpression() returns an expression
        # (col1, col2,..) > (memo1, memo2...) for ascending sort order.
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset, self.logError)
        expressions = [Person.id, Person.name]
        limits = [1, 'foo']
        limit_expression = range_factory.lessThanOrGreaterThanExpression(
            expressions, limits)
        self.assertEqual(
            "(Person.id, Person.name) > (1, 'foo')",
            compile(limit_expression))

    def test_lessThanOrGreaterThanExpression__desc(self):
        # beforeOrAfterExpression() returns an expression
        # (col1, col2,..) < (memo1, memo2...) for descending sort order.
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset, self.logError)
        expressions = [Desc(Person.id), Desc(Person.name)]
        limits = [1, 'foo']
        limit_expression = range_factory.lessThanOrGreaterThanExpression(
            expressions, limits)
        self.assertEqual(
            "(Person.id, Person.name) < (1, 'foo')",
            compile(limit_expression))

    def test_equalsExpressionsFromLimits(self):
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset, self.logError)
        order_by = [
            Person.id, Person.datecreated, Desc(Person.name),
            Desc(Person.displayname)]
        limits = [
            1, datetime(2011, 07, 25, 0, 0, 0, tzinfo=pytz.UTC), 'foo', 'bar']
        limits = range_factory.limitsGroupedByOrderDirection(order_by, limits)
        equals_expressions = range_factory.equalsExpressionsFromLimits(limits)
        equals_expressions = map(compile, equals_expressions)
        self.assertEqual(
            ['Person.id = ?', 'Person.datecreated = ?', 'Person.name = ?',
             'Person.displayname = ?'],
            equals_expressions)

    def test_whereExpressions__asc(self):
        """For ascending sort order, whereExpressions() returns the
        WHERE clause expression > memo.
        """
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset, self.logError)
        [where_clause] = range_factory.whereExpressions([Person.id], [1])
        self.assertEquals('(Person.id) > (1)', compile(where_clause))

    def test_whereExpressions_desc(self):
        """For descending sort order, whereExpressions() returns the
        WHERE clause expression < memo.
        """
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset, self.logError)
        [where_clause] = range_factory.whereExpressions(
            [Desc(Person.id)], [1])
        self.assertEquals('(Person.id) < (1)', compile(where_clause))

    def test_whereExpressions__two_sort_columns_asc_asc(self):
        """If the ascending sort columns c1, c2 and the memo values
        m1, m2 are specified, whereExpressions() returns a WHERE
        expressions comparing the tuple (c1, c2) with the memo tuple
        (m1, m2):

        (c1, c2) > (m1, m2)
        """
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset, self.logError)
        [where_clause] = range_factory.whereExpressions(
            [Person.id, Person.name], [1, 'foo'])
        self.assertEquals(
            "(Person.id, Person.name) > (1, 'foo')", compile(where_clause))

    def test_whereExpressions__two_sort_columns_desc_desc(self):
        """If the descending sort columns c1, c2 and the memo values
        m1, m2 are specified, whereExpressions() returns a WHERE
        expressions comparing the tuple (c1, c2) with the memo tuple
        (m1, m2):

        (c1, c2) < (m1, m2)
        """
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset, self.logError)
        [where_clause] = range_factory.whereExpressions(
            [Desc(Person.id), Desc(Person.name)], [1, 'foo'])
        self.assertEquals(
            "(Person.id, Person.name) < (1, 'foo')", compile(where_clause))

    def test_whereExpressions__two_sort_columns_asc_desc(self):
        """If the ascending sort column c1, the descending sort column
        c2 and the memo values m1, m2 are specified, whereExpressions()
        returns two expressions where  the first expression is

            c1 == m1 AND c2 < m2

        and the second expression is

            c1 > m1
        """
        resultset = self.makeStormResultSet()
        range_factory = StormRangeFactory(resultset, self.logError)
        [where_clause_1, where_clause_2] = range_factory.whereExpressions(
            [Person.id, Desc(Person.name)], [1, 'foo'])
        self.assertEquals(
            "Person.id = ? AND ((Person.name) < ('foo'))",
            compile(where_clause_1))
        self.assertEquals('(Person.id) > (1)', compile(where_clause_2))

    def test_getSlice__forward_without_memo(self):
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.name, Person.id)
        all_results = list(resultset)
        range_factory = StormRangeFactory(resultset)
        sliced_result = range_factory.getSlice(3)
        self.assertEqual(all_results[:3], list(sliced_result))

    def test_getSlice__forward_with_memo(self):
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.name, Person.id)
        all_results = list(resultset)
        memo = simplejson.dumps([all_results[0].name, all_results[0].id])
        range_factory = StormRangeFactory(resultset)
        sliced_result = range_factory.getSlice(3, memo)
        self.assertEqual(all_results[1:4], list(sliced_result))

    def test_getSlice__backward_without_memo(self):
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.name, Person.id)
        all_results = list(resultset)
        expected = all_results[-3:]
        expected.reverse()
        range_factory = StormRangeFactory(resultset)
        sliced_result = range_factory.getSlice(3, forwards=False)
        self.assertEqual(expected, list(sliced_result))

    def test_getSlice_backward_with_memo(self):
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.name, Person.id)
        all_results = list(resultset)
        expected = all_results[1:4]
        expected.reverse()
        memo = simplejson.dumps([all_results[4].name, all_results[4].id])
        range_factory = StormRangeFactory(resultset)
        sliced_result = range_factory.getSlice(3, memo, forwards=False)
        self.assertEqual(expected, list(sliced_result))

    def makeResultSetWithPartiallyIdenticalSortData(self):
        # Create a result set, where each value of
        # LibraryFileAlias.filename and of LibraryFileAlias.mimetype
        # appears twice. (Note that Bug.bugattachments returns a
        # DecoratedResultSet, where the Storm query returns
        # LibraryFileAlias rows too.)
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            for filename in ('file-a', 'file-b'):
                for content_type in ('text/a', 'text/b'):
                    for count in range(2):
                        self.factory.makeBugAttachment(
                            bug=bug, owner=bug.owner, filename=filename,
                            content_type=content_type)
        return bug.attachments

    def test_getSlice__multiple_sort_columns(self):
        # Slicing works if the result set is ordered by more than
        # one column, and if the result contains rows with identical
        resultset = self.makeResultSetWithPartiallyIdenticalSortData()
        resultset.order_by(
            LibraryFileAlias.mimetype, LibraryFileAlias.filename,
            LibraryFileAlias.id)
        all_results = list(resultset)
        # We have two results
        # The third and fourth row have identical filenames and
        # mime types, but the LibraryFileAlias IDs are different
        # If we use the values from the third row as memo parameters
        # for a forward batch, the slice of this btach starts with
        # the fourth row of the entire result set.
        memo_lfa = all_results[2].libraryfile
        memo = simplejson.dumps(
            [memo_lfa.mimetype, memo_lfa.filename, memo_lfa.id])
        range_factory = StormRangeFactory(resultset)
        sliced_result = range_factory.getSlice(3, memo)
        self.assertEqual(all_results[3:6], list(sliced_result))

    def test_getSlice__decorated_resultset(self):
        resultset = self.makeDecoratedStormResultSet()
        resultset.order_by(LibraryFileAlias.id)
        all_results = list(resultset)
        plain_results = list(resultset.get_plain_result_set())
        memo = simplejson.dumps([resultset.get_plain_result_set()[0][1].id])
        range_factory = StormRangeFactory(resultset)
        sliced_result = range_factory.getSlice(3, memo)
        self.assertEqual(all_results[1:4], list(sliced_result))
        self.assertEqual(plain_results[1:4], sliced_result.shadow_values)

    def test_getSlice__returns_ShadowedList(self):
        # getSlice() returns lists.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.id)
        range_factory = StormRangeFactory(resultset)
        sliced_result = range_factory.getSlice(3)
        self.assertIsInstance(sliced_result, ShadowedList)

    def test_getSlice__backwards_then_forwards(self):
        # A slice can be retrieved in both directions from one factory.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.id)
        all_results = list(resultset)
        memo = simplejson.dumps([all_results[2].id])
        range_factory = StormRangeFactory(resultset)
        backward_slice = range_factory.getSlice(
            size=2, endpoint_memo=memo, forwards=False)
        backward_slice.reverse()
        self.assertEqual(all_results[:2], list(backward_slice))
        forward_slice = range_factory.getSlice(
            size=2, endpoint_memo=memo, forwards=True)
        self.assertEqual(all_results[3:5], list(forward_slice))

    def makeStringSequence(self, sequence):
        return [str(elem) for elem in sequence]

    def test_ShadowedList__init(self):
        # ShadowedList instances need two lists as constructor parametrs.
        list1 = range(3)
        list2 = self.makeStringSequence(list1)
        shadowed_list = ShadowedList(list1, list2)
        self.assertEqual(shadowed_list.values, list1)
        self.assertEqual(shadowed_list.shadow_values, list2)

    def test_ShadowedList__init__non_sequence_parameter(self):
        # values and shadow_values must be sequences.
        self.assertRaises(TypeError, ShadowedList, 1, range(3))
        self.assertRaises(TypeError, ShadowedList, range(3), 1)

    def test_ShadowedList__init__different_list_lengths(self):
        # values and shadow_values must have the same length.
        self.assertRaises(ValueError, ShadowedList, range(2), range(3))

    def test_ShadowedList__len(self):
        # The length of a ShadowedList ist the same as the list of
        # the sequences it stores.
        list1 = range(3)
        list2 = self.makeStringSequence(list1)
        self.assertEqual(len(list1), len(ShadowedList(list1, list2)))

    def test_ShadowedList__slice(self):
        # A slice of a ShadowedList contains the slices of its
        # values and shaow_values.
        list1 = range(5)
        list2 = self.makeStringSequence(list1)
        shadowed_list = ShadowedList(list1, list2)
        self.assertEqual(list1[2:4], shadowed_list[2:4].values)
        self.assertEqual(list2[2:4], shadowed_list[2:4].shadow_values)

    def test_ShadowedList__getitem(self):
        # Accessing a single element of a ShadowedList is equivalent to
        # accessig an element of its values attribute.
        list1 = range(3)
        list2 = self.makeStringSequence(list1)
        shadowed_list = ShadowedList(list1, list2)
        self.assertEqual(list1[1], shadowed_list[1])

    def test_ShadowedList__add(self):
        # Two shadowedLists can be added, yielding another ShadowedList.
        list1 = range(3)
        list2 = self.makeStringSequence(list1)
        shadow_list1 = ShadowedList(list1, list2)
        list3 = range(4)
        list4 = self.makeStringSequence(list3)
        shadow_list2 = ShadowedList(list3, list4)
        list_sum = shadow_list1 + shadow_list2
        self.assertIsInstance(list_sum, ShadowedList)
        self.assertEqual(list1 + list3, list_sum.values)
        self.assertEqual(list2 + list4, list_sum.shadow_values)

    def test_ShadowedList__iterator(self):
        # Iterating over a ShadowedList yields if values elements.
        list1 = range(3)
        list2 = self.makeStringSequence(list1)
        shadow_list = ShadowedList(list1, list2)
        self.assertEqual(list1, list(iter(shadow_list)))

    def test_ShadowedList__reverse(self):
        # ShadowList.reverse() reverses its elements.
        list1 = range(3)
        list2 = self.makeStringSequence(list1)
        first1 = list1[0]
        last1 = list1[-1]
        first2 = list2[0]
        last2 = list2[-1]
        shadow_list = ShadowedList(list1, list2)
        shadow_list.reverse()
        self.assertEqual(first1, shadow_list[-1])
        self.assertEqual(last1, shadow_list[0])
        self.assertEqual(first2, shadow_list.shadow_values[-1])
        self.assertEqual(last2, shadow_list.shadow_values[0])

    def test_ShadowedList__reverse__values_and_shadow_values_identical(self):
        # ShadowList.reverse() works also when passed the same
        # sequence as values and as shadow_values.
        list_ = range(3)
        shadow_list = ShadowedList(list_, list_)
        shadow_list.reverse()
        self.assertEqual(0, shadow_list[-1])
        self.assertEqual(2, shadow_list[0])
        self.assertEqual(0, shadow_list.shadow_values[-1])
        self.assertEqual(2, shadow_list.shadow_values[0])

    def test_rough_length(self):
        # StormRangeFactory.rough_length returns an estimate of the
        # length of the result set.
        resultset = self.makeStormResultSet()
        resultset.order_by(Person.id)
        range_factory = StormRangeFactory(resultset)
        estimated_length = range_factory.rough_length
        self.assertThat(estimated_length, LessThan(10))
        self.assertThat(estimated_length, Not(LessThan(1)))

    def test_rough_length_first_sort_column_desc(self):
        # StormRangeFactory.rough_length can handle result sets where
        # the first sort column has descendig order.
        resultset = self.makeStormResultSet()
        resultset.order_by(Desc(Person.id))
        range_factory = StormRangeFactory(resultset)
        estimated_length = range_factory.rough_length
        self.assertThat(estimated_length, LessThan(10))
        self.assertThat(estimated_length, Not(LessThan(1)))

    def test_rough_length_decorated_result_set(self):
        # StormRangeFactory.rough_length can handle DecoratedResultSets.
        resultset = self.makeDecoratedStormResultSet()
        range_factory = StormRangeFactory(resultset)
        estimated_length = range_factory.rough_length
        self.assertThat(estimated_length, LessThan(10))
        self.assertThat(estimated_length, Not(LessThan(1)))

    def test_rough_length_distinct_query(self):
        # StormRangeFactory.rough_length with SELECT DISTINCT queries.
        resultset = self.makeStormResultSet()
        resultset.config(distinct=True)
        resultset.order_by(Person.name, Person.id)
        range_factory = StormRangeFactory(resultset)
        estimated_length = range_factory.rough_length
        self.assertThat(estimated_length, LessThan(10))
        self.assertThat(estimated_length, Not(LessThan(1)))

    def test_getSliceByIndex__storm_result_set(self):
        # StormRangeFactory.getSliceByIndex() returns a slice of the
        # resultset, wrapped into a ShadowedList. For plain Storm
        # result sets, the main values and the shadow values are both
        # the corresponding elements of the result set.
        resultset = self.makeStormResultSet()
        all_results = list(resultset)
        range_factory = StormRangeFactory(resultset)
        sliced = range_factory.getSliceByIndex(2, 4)
        self.assertIsInstance(sliced, ShadowedList)
        self.assertEqual(all_results[2:4], list(sliced))
        self.assertEqual(all_results[2:4], sliced.shadow_values)

    def test_getSliceByIndex__decorated_result_set(self):
        # StormRangeFactory.getSliceByIndex() returns a slice of the
        # resultset, wrapped into a ShadowedList. For decorated Storm
        # result sets, the main values are the corresponding values of
        # the decorated result set and the shadow values are the
        # corresponding elements of the plain result set.
        resultset = self.makeDecoratedStormResultSet()
        all_results = list(resultset)
        all_undecorated_results = list(resultset.get_plain_result_set())
        range_factory = StormRangeFactory(resultset)
        sliced = range_factory.getSliceByIndex(2, 4)
        self.assertIsInstance(sliced, ShadowedList)
        self.assertEqual(all_results[2:4], list(sliced))
        self.assertEqual(all_undecorated_results[2:4], sliced.shadow_values)

    def assertEmptyResultSetsWorking(self, range_factory):
        # getSlice() and getSliceByIndex() return empty ShadowedLists.
        sliced = range_factory.getSlice(1)
        self.assertEqual([], sliced.values)
        self.assertEqual([], sliced.shadow_values)
        sliced = range_factory.getSliceByIndex(0, 1)
        self.assertEqual([], sliced.values)
        self.assertEqual([], sliced.shadow_values)
        # The endpoint memos are empty strings.
        request = LaunchpadTestRequest()
        batchnav = BatchNavigator(
            range_factory.resultset, request, size=3,
            range_factory=range_factory)
        first, last = range_factory.getEndpointMemos(batchnav.batch)
        self.assertEqual('', first)
        self.assertEqual('', last)

    def test_StormRangeFactory__EmptyResultSet(self):
        # It is possible to create StormRangeFactory instances for
        # EmptyResultSets,
        resultset = EmptyResultSet()
        range_factory = StormRangeFactory(resultset)
        self.assertEqual(0, range_factory.rough_length)
        self.assertEmptyResultSetsWorking(range_factory)

    def test_StormRangeFactory__empty_real_resultset(self):
        # StormRangeFactory works with empty regular result sets,
        product = self.factory.makeProduct()
        resultset = product.development_focus.searchTasks(
            BugTaskSet().open_bugtask_search)
        self.assertEqual(0, resultset.count())
        range_factory = StormRangeFactory(resultset)
        # rough_length is supposed to be zero, but the ANALYZE SELECT
        # is not always precise.
        self.assertThat(range_factory.rough_length, LessThan(10))
        self.assertEmptyResultSetsWorking(range_factory)
