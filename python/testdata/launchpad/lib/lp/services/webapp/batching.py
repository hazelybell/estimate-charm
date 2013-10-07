# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import datetime
from operator import isSequenceType
import re

from iso8601 import (
    parse_date,
    ParseError,
    )
import lazr.batchnavigator
from lazr.batchnavigator.interfaces import IRangeFactory
import simplejson
from storm import Undef
from storm.expr import (
    And,
    compile,
    Desc,
    Or,
    SQL,
    )
from storm.properties import PropertyColumn
from storm.store import EmptyResultSet
from storm.zope.interfaces import IResultSet
from zope.component import adapts
from zope.interface import implements
from zope.interface.common.sequence import IFiniteSequence
from zope.security.proxy import (
    isinstance as zope_isinstance,
    ProxyFactory,
    removeSecurityProxy,
    )

from lp.services.config import config
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.interfaces import ISlaveStore
from lp.services.database.sqlbase import (
    convert_storm_clause_to_string,
    sqlvalues,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp.interfaces import (
    ITableBatchNavigator,
    StormRangeFactoryError,
    )
from lp.services.webapp.publisher import LaunchpadView


class FiniteSequenceAdapter:

    adapts(IResultSet)
    implements(IFiniteSequence)

    def __init__(self, context):
        self.context = context

    def __getitem__(self, ix):
        return self.context[ix]

    def __iter__(self):
        return iter(self.context)

    def __len__(self):
        return self.context.count()


class BoundReferenceSetAdapter:
    """Adaptor for `BoundReferenceSet` implementations in Storm."""

    implements(IFiniteSequence)

    def __init__(self, context):
        self.context = context

    def __getitem__(self, ix):
        return self.context.find()[ix]

    def __iter__(self):
        return iter(self.context)

    def __len__(self):
        return self.context.count()


class UpperBatchNavigationView(LaunchpadView):
    """Only render navigation links if there is a batch."""

    css_class = "upper-batch-nav"

    def render(self):
        if self.context.currentBatch():
            return LaunchpadView.render(self)
        return u""


class LowerBatchNavigationView(UpperBatchNavigationView):
    css_class = "lower-batch-nav"


class BatchNavigator(lazr.batchnavigator.BatchNavigator):

    def __init__(self, results, request, start=0, size=None, callback=None,
                 transient_parameters=None, force_start=False,
                 range_factory=None, hide_counts=False):
        super(BatchNavigator, self).__init__(results, request,
            start=start, size=size, callback=callback,
            transient_parameters=transient_parameters,
            force_start=force_start, range_factory=range_factory)
        self.hide_counts = hide_counts

    @property
    def default_batch_size(self):
        return config.launchpad.default_batch_size

    @property
    def max_batch_size(self):
        return config.launchpad.max_batch_size

    @property
    def has_multiple_pages(self):
        """Whether the total size is greater than the batch size.

        When true, it means that the batch should be rendered on multiple
        pages, and a navigation heading should be included above and below the
        table.
        """
        return self.batch.total() > self.batch.size


class ActiveBatchNavigator(BatchNavigator):
    """A paginator for active items.

    Used when a view needs to display two BatchNavigators.
    """
    variable_name_prefix = 'active'


class InactiveBatchNavigator(BatchNavigator):
    """A paginator for inactive items.

    Used when a view needs to display two Batchavigators.
    """
    variable_name_prefix = 'inactive'


class TableBatchNavigator(BatchNavigator):
    """See lp.services.webapp.interfaces.ITableBatchNavigator."""
    implements(ITableBatchNavigator)

    def __init__(self, results, request, start=0, size=None,
                 columns_to_show=None, callback=None):
        BatchNavigator.__init__(self, results, request, start, size, callback)

        self.show_column = {}
        if columns_to_show:
            for column_to_show in columns_to_show:
                self.show_column[column_to_show] = True


class DateTimeJSONEncoder(simplejson.JSONEncoder):
    """A JSON encoder that understands datetime objects.

    Datetime objects are formatted according to ISO 1601.
    """
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return simplejson.JSONEncoder.default(self, obj)


class ShadowedList:
    """A (partial) sequence impementation which maintains two
    sequences: A publicly visible one and a "shadow" sequence.

    Background: StormRangeFactory.getSlice() returns a sequence
    of records which is used in lazr.batchnavigator.Batchnavigator
    and in lazr.batchnavigator.z3batching.Batch.

    This slice is passed back by Batch.nextBatch() and Batch.prevBatch()
    to StormRangeFactory.getEndpointMemos().

    StormRangeFactory can work with DecoratedResultSets, which means
    that the data required to create the memo values may only be
    available in the plain, undecorated, result set.

    This class allows to maintain the values needed by BachNavigator
    and Batch as well as the values needed by
    StormRangeFactory.getEndpointMemos().

    It implements only those parts of the sequence protocol needed by
    BatchNavigator and Batch.
    """
    def __init__(self, values, shadow_values):
        if not isSequenceType(values) or not isSequenceType(shadow_values):
            raise TypeError("values and shadow_values must be sequences.")
        if len(values) != len(shadow_values):
            raise ValueError(
                "values and shadow_values must have the same length.")
        self.values = values
        # Store always a copy: values and shadow_values may be identical,
        # and if this is the case, the two reverse() calls in the method
        # reverse() below will cancel each other.
        self.shadow_values = shadow_values[:]

    def __len__(self):
        """See `list`."""
        return len(self.values)

    def __getslice__(self, start, end):
        """See `list`."""
        return ShadowedList(
            self.values[start:end], self.shadow_values[start:end])

    def __getitem__(self, index):
        """See `list`."""
        return self.values[index]

    def __add__(self, other):
        """See `list`."""
        if not isinstance(other, ShadowedList):
            raise TypeError(
                'You can only add another ShadowedList to a ShadowedList')
        return ShadowedList(
            self.values + other.values,
            self.shadow_values + other.shadow_values)

    def __iter__(self):
        """See `list`."""
        return iter(self.values)

    def reverse(self):
        self.values.reverse()
        self.shadow_values.reverse()


def plain_expression(expression):
    """Strip an optional DESC() from an expression."""
    if isinstance(expression, Desc):
        return expression.expr
    else:
        return expression


class StormRangeFactory:
    """A range factory for Storm result sets.

    It creates the endpoint memo values from the expressions used in the
    ORDER BY clause.

    Limitations:

    - The order_by expressions must be Storm PropertyColumn instances,
      e.g. Bug.title. Simple strings (e.g., resultset.order_by('Bug.id')
      or general Storm SQL expression are not supported.
    - The objects representing rows of the PropertyColumn's table must
      be contained in the result. I.e.,

          store.find(Bug.id, Bug.id < 10)

      does not work, while

          store.find(Bug, Bug.id < 10)

      works.

    Note: This factory assumes that the result set is fully sorted,
    i.e. that the set of the column values used for sorting is
    distinct for each result row.
    """
    implements(IRangeFactory)

    def __init__(self, resultset, error_cb=None):
        """Create a new StormRangeFactory instance.

        :param resultset: A Storm ResultSet instance or a DecoratedResultSet
            instance.
        :param error_cb: A function which takes one string as a parameter.
            It is called when the parameter endpoint_memo of getSlice()
            does not match the order settings of a resultset.
        """
        self.resultset = resultset
        if zope_isinstance(resultset, DecoratedResultSet):
            self.plain_resultset = resultset.get_plain_result_set()
        else:
            self.plain_resultset = resultset
        self.error_cb = error_cb
        if not self.empty_resultset:
            self.forward_sort_order = self.getOrderBy()
            if self.forward_sort_order is Undef:
                raise StormRangeFactoryError(
                    'StormRangeFactory requires a sorted result set.')
            self.backward_sort_order = self.reverseSortOrder()

    @property
    def empty_resultset(self):
        return zope_isinstance(self.plain_resultset, EmptyResultSet)

    def getOrderBy(self):
        """Return the order_by expressions of the result set."""
        return removeSecurityProxy(self.plain_resultset)._order_by

    def getOrderValuesFor(self, row):
        """Return the values of the order_by expressions for the given row.
        """
        sort_values = []
        if not zope_isinstance(row, tuple):
            row = (row, )
        sort_expressions = self.getOrderBy()
        for expression in sort_expressions:
            expression = plain_expression(expression)
            if not zope_isinstance(expression, PropertyColumn):
                raise StormRangeFactoryError(
                    'StormRangeFactory only supports sorting by '
                    'PropertyColumn, not by %r.' % expression)
            class_instance_found = False
            for row_part in row:
                if zope_isinstance(row_part, expression.cls):
                    sort_values.append(expression.__get__(row_part))
                    class_instance_found = True
                    break
            if not class_instance_found:
                raise StormRangeFactoryError(
                    'Instances of %r are not contained in the result set, '
                    'but are required to retrieve the value of %s.%s.'
                    % (expression.cls, expression.cls.__name__,
                       expression.name))
        return sort_values

    def getEndpointMemos(self, batch):
        """See `IRangeFactory`."""
        plain_slice = batch.sliced_list.shadow_values
        if len(plain_slice) == 0:
            return ('', '')
        lower = self.getOrderValuesFor(plain_slice[0])
        upper = self.getOrderValuesFor(plain_slice[batch.trueSize - 1])
        return (
            simplejson.dumps(lower, cls=DateTimeJSONEncoder),
            simplejson.dumps(upper, cls=DateTimeJSONEncoder),
            )

    def reportError(self, message):
        if self.error_cb is not None:
            self.error_cb(message)

    def parseMemo(self, memo):
        """Convert the given memo string into a sequence of Python objects.

        memo should be a JSON string as returned by getEndpointMemos().

        Note that memo originates from a URL query parameter and can thus
        not be trusted to always contain formally valid and consistent
        data.

        Parsing errors or data not matching the sort parameters of the
        result set are simply ignored.
        """
        if memo == '':
            return None
        try:
            parsed_memo = simplejson.loads(memo)
        except simplejson.JSONDecodeError:
            self.reportError('memo is not a valid JSON string.')
            return None
        if not isinstance(parsed_memo, list):
            self.reportError(
                'memo must be the JSON representation of a list.')
            return None

        sort_expressions = self.getOrderBy()
        if len(sort_expressions) != len(parsed_memo):
            self.reportError(
                'Invalid number of elements in memo string. '
                'Expected: %i, got: %i'
                % (len(sort_expressions), len(parsed_memo)))
            return None

        converted_memo = []
        for expression, value in zip(sort_expressions, parsed_memo):
            expression = plain_expression(expression)
            try:
                expression.variable_factory(value=value)
            except TypeError as error:
                # A TypeError is raised when the type of value cannot
                # be used for expression. All expected types are
                # properly created by simplejson.loads() above, except
                # time stamps which are represented as strings in
                # ISO format. If value is a string and if it can be
                # converted into a datetime object, we have a valid
                # value.
                if (str(error).startswith('Expected datetime') and
                    isinstance(value, str)):
                    try:
                        value = parse_date(value)
                    except (ParseError, ValueError):
                        # We get a ParseError if value does not match
                        # a certain regex, and we get a ValueError
                        # for formally correct but invalid dates,
                        # like May 35.
                        self.reportError('Invalid datetime value: %r' % value)
                        return None
                else:
                    self.reportError(
                        'Invalid parameter: %r' % value)
                    return None
            converted_memo.append(value)
        return converted_memo

    def reverseSortOrder(self):
        """Return a list of reversed sort expressions."""
        def invert_sort_expression(expr):
            if isinstance(expr, Desc):
                return expr.expr
            else:
                return Desc(expr)

        return [
            invert_sort_expression(expression)
            for expression in self.getOrderBy()]

    def limitsGroupedByOrderDirection(self, sort_expressions, memos):
        """Group sort expressions and memo values by order direction."""
        descending = isinstance(sort_expressions[0], Desc)
        grouped_limits = []
        expression_group = []
        memo_group = []
        for expression, memo in zip(sort_expressions, memos):
            if descending == isinstance(expression, Desc):
                expression_group.append(expression)
                memo_group.append(memo)
            else:
                grouped_limits.append((expression_group, memo_group))
                descending = isinstance(expression, Desc)
                expression_group = [expression]
                memo_group = [memo]
        grouped_limits.append((expression_group, memo_group))
        return grouped_limits

    def lessThanOrGreaterThanExpression(self, expressions, memos):
        """Return an SQL expression "(expressions) OP (memos)".

        OP is >, if the elements of expressions are PropertyColumns; else
        the elements of expressions are instances of Desc(PropertyColumn)
        and OP is <.
        """
        descending = isinstance(expressions[0], Desc)
        if descending:
            expressions = [expression.expr for expression in expressions]
        expressions = map(compile, expressions)
        expressions = ', '.join(expressions)
        memos = ', '.join(sqlvalues(*memos))
        if descending:
            return SQL('(%s) < (%s)' % (expressions, memos))
        else:
            return SQL('(%s) > (%s)' % (expressions, memos))

    def equalsExpressionsFromLimits(self, limits):
        """Return a list [expression == memo, ...] for the given limits."""

        result = []
        for expressions, memos in limits:
            result.extend(
                plain_expression(expression) == memo
                for expression, memo in zip(expressions, memos))
        return result

    def whereExpressionsFromGroupedLimits(self, limits):
        """Build a sequence of WHERE expressions from the given limits.

        limits is a list of tuples (expressions, memos), where
        expressions is a list of PropertyColumn instances or of
        instances of Desc(PropertyColumn). Desc(PropertyColumn)
        and PropertyColumn instances must not appear in the same
        expressions list.

        memos are the memo values asociated with the columns in
        expressions.

        Given a limits value of
            [([c11, c12 ...], [m11, m12 ...]),
             ([c21, c22 ...], [m21, m22 ...]),
             ...
             ([cN1, cN2 ...], [mN1, mN2 ...])]

        this method returns a sequence of these Storm/SQL expressions:

            * (c11, c12 ...) = (m11, m12 ...) AND
              (c21, c22 ...) = (m21, m22 ...) AND
              ...
              (cN1, cN2 ...) < (mN1, mN2 ...)
            * (c11, c12 ...) = (m11, m12 ...) AND
              (c21, c22 ...) = (m21, m22 ...) AND
              ...
              (cM1, cM2 ...) < (mM1, mM2 ...)

              (where M = N - 1)
            ...
            * (c11, c12 ...) < (m11, m12 ...)

        The getSlice() should return rows matching any of these
        expressions. Note that the result sets returned by each
        expression are disjuct, hence they can be simply ORed,
        as well as used in a UNION ALL query.
        """
        start = limits[:-1]
        last_expressions, last_memos = limits[-1]
        last_clause = self.lessThanOrGreaterThanExpression(
            last_expressions, last_memos)
        if len(start) > 0:
            clauses = self.equalsExpressionsFromLimits(start)
            clauses.append(last_clause)
            clauses = [And(*clauses)]
            return clauses + self.whereExpressionsFromGroupedLimits(start)
        else:
            return [last_clause]

    def whereExpressions(self, sort_expressions, memos):
        """WHERE expressions for the given sort columns and memos values."""
        grouped_limits = self.limitsGroupedByOrderDirection(
            sort_expressions, memos)
        return self.whereExpressionsFromGroupedLimits(grouped_limits)

    def getSliceFromMemo(self, size, memo):
        """Return a result set for the given memo values.

        Note that at least two other implementations are possible:
        Instead of OR-combining the expressions returned by
        whereExpressions(), these expressions could be used for
        separate SELECTs which are then merged with UNION ALL.

        We could also issue separate Storm queries for each
        expression and combine the results here.

        Which variant is more efficient is yet unknown; it may
        differ between different queries.
        """
        sort_expressions = self.getOrderBy()
        where = self.whereExpressions(sort_expressions, memo)
        where = reduce(Or, where)
        # From storm.zope.interfaces.IResultSet.__doc__:
        #     - C{find()}, C{group_by()} and C{having()} are really
        #       used to configure result sets, so are mostly intended
        #       for use on the model side.
        naked_result = removeSecurityProxy(self.resultset).find(where)
        result = ProxyFactory(naked_result)
        return result.config(limit=size)

    def _get_shadowed_list(self, result):
        if zope_isinstance(result, DecoratedResultSet):
            items = list(result.copy().config(return_both=True))
            if items:
                shadow_result, real_result = map(list, zip(*items))
            else:
                shadow_result = real_result = []
        else:
            shadow_result = real_result = list(result)
        return ShadowedList(real_result, shadow_result)

    def getSlice(self, size, endpoint_memo='', forwards=True):
        """See `IRangeFactory`."""
        if self.empty_resultset:
            return ShadowedList([], [])
        if forwards:
            self.resultset.order_by(*self.forward_sort_order)
        else:
            self.resultset.order_by(*self.backward_sort_order)

        parsed_memo = self.parseMemo(endpoint_memo)
        # Note that lazr.batchnavigator calls len(slice), so we can't
        # return the plain result set.
        if parsed_memo is None:
            result = self.resultset.config(limit=size)
        else:
            result = self.getSliceFromMemo(size, parsed_memo)
        return self._get_shadowed_list(result)

    def getSliceByIndex(self, start, end):
        """See `IRangeFactory."""
        sliced = self.resultset[start:end]
        return self._get_shadowed_list(sliced)

    @cachedproperty
    def rough_length(self):
        """See `IRangeFactory."""
        from lp.services.librarian.model import LibraryFileAlias
        # get_select_expr() requires at least one column as a parameter.
        # getorderBy() already knows about columns that can appear
        # in the result set, so let's use them. Moreover, for SELECT
        # DISTINCT queries, each column used for sorting must appear
        # in the result.
        if self.empty_resultset:
            return 0
        columns = [plain_expression(column) for column in self.getOrderBy()]
        select = removeSecurityProxy(self.plain_resultset).get_select_expr(
            *columns)
        explain = 'EXPLAIN ' + convert_storm_clause_to_string(select)
        result = ISlaveStore(LibraryFileAlias).execute(explain)
        _rows_re = re.compile("rows=(\d+)\swidth=")
        first_line = result.get_one()[0]
        match = _rows_re.search(first_line)
        if match is None:
            raise RuntimeError(
                "Unexpected EXPLAIN output %s" % repr(first_line))
        return int(match.group(1))
