# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'AdvisoryUnlock',
    'Array',
    'ArrayAgg',
    'ArrayContains',
    'ArrayIntersects',
    'BulkUpdate',
    'ColumnSelect',
    'Concatenate',
    'CountDistinct',
    'fti_search',
    'Greatest',
    'get_where_for_reference',
    'IsDistinctFrom',
    'NullCount',
    'rank_by_fti',
    'TryAdvisoryLock',
    'Unnest',
    'Values',
    ]

from storm import Undef
from storm.exceptions import ClassInfoError
from storm.expr import (
    BinaryOper,
    COLUMN_NAME,
    ComparableExpr,
    compile,
    CompoundOper,
    EXPR,
    Expr,
    In,
    NamedFunc,
    Or,
    SQL,
    TABLE,
    )
from storm.info import (
    get_cls_info,
    get_obj_info,
    )


class BulkUpdate(Expr):
    # Perform a bulk table update using literal values.
    __slots__ = ("map", "where", "table", "values")

    def __init__(self, map, table, values, where=Undef):
        self.map = map
        self.where = where
        self.table = table
        self.values = values


@compile.when(BulkUpdate)
def compile_bulkupdate(compile, update, state):
    pairs = update.map.items()
    state.push("context", COLUMN_NAME)
    col_names = [compile(col, state, token=True) for col, val in pairs]
    state.context = EXPR
    col_values = [compile(val, state) for col, val in pairs]
    sets = ["%s=%s" % (col, val) for col, val in zip(col_names, col_values)]
    state.context = TABLE
    tokens = ["UPDATE ", compile(update.table, state, token=True), " SET ",
              ", ".join(sets), " FROM "]
    state.context = EXPR
    # We don't want the values expression wrapped in parenthesis.
    state.precedence = 0
    tokens.append(compile(update.values, state, raw=True))
    if update.where is not Undef:
        tokens.append(" WHERE ")
        tokens.append(compile(update.where, state, raw=True))
    state.pop()
    return "".join(tokens)


class Values(Expr):
    __slots__ = ("name", "cols", "values")

    def __init__(self, name, cols, values):
        self.name = name
        self.cols = cols
        self.values = values


@compile.when(Values)
def compile_values(compile, expr, state):
    col_names, col_types = zip(*expr.cols)
    first_row = ", ".join(
        "%s::%s" % (compile(value, state), type)
        for value, type in zip(expr.values[0], col_types))
    rows = [first_row] + [compile(value, state) for value in expr.values[1:]]
    return "(VALUES (%s)) AS %s(%s)" % (
        "), (".join(rows), expr.name, ', '.join(col_names))


class ColumnSelect(Expr):
    # Wrap a select statement in braces so that it can be used as a column
    # expression in another query.
    __slots__ = ("select")

    def __init__(self, select):
        self.select = select


@compile.when(ColumnSelect)
def compile_columnselect(compile, expr, state):
    state.push("context", EXPR)
    select = compile(expr.select)
    state.pop()
    return "(%s)" % select


class Greatest(NamedFunc):
    # XXX wallyworld 2011-01-31 bug=710466:
    # We need to use a Postgres greatest() function call but Storm
    # doesn't support that yet.
    __slots__ = ()
    name = "GREATEST"


class CountDistinct(Expr):
    # XXX: wallyworld 2010-11-26 bug=675377:
    # storm's Count() implementation is broken for distinct with > 1
    # column.

    __slots__ = ("columns")

    def __init__(self, columns):
        self.columns = columns


@compile.when(CountDistinct)
def compile_countdistinct(compile, countselect, state):
    state.push("context", EXPR)
    col = compile(countselect.columns)
    state.pop()
    return "count(distinct(%s))" % col


class Concatenate(BinaryOper):
    """Storm operator for string concatenation."""
    __slots__ = ()
    oper = " || "


class NullCount(NamedFunc):
    __slots__ = ()
    name = "NULL_COUNT"


class Array(ComparableExpr):
    __slots__ = ("args",)

    def __init__(self, *args):
        self.args = args


class TryAdvisoryLock(NamedFunc):

    __slots__ = ()

    name = 'PG_TRY_ADVISORY_LOCK'


class AdvisoryUnlock(NamedFunc):

    __slots__ = ()

    name = 'PG_ADVISORY_UNLOCK'


@compile.when(Array)
def compile_array(compile, array, state):
    state.push("context", EXPR)
    args = compile(array.args, state)
    state.pop()
    return "ARRAY[%s]" % args


class ArrayAgg(NamedFunc):
    """Aggregate values (within a GROUP BY) into an array."""
    __slots__ = ()
    name = "ARRAY_AGG"


class Unnest(NamedFunc):
    """Expand an array to a set of rows."""
    __slots__ = ()
    name = "unnest"


class ArrayContains(CompoundOper):
    """True iff the left side is a superset of the right side."""
    __slots__ = ()
    oper = "@>"


class ArrayIntersects(CompoundOper):
    """True iff the arrays have at least one element in common."""
    __slots__ = ()
    oper = "&&"


class IsDistinctFrom(CompoundOper):
    """True iff the left side is distinct from the right side."""
    __slots__ = ()
    oper = " IS DISTINCT FROM "


def get_where_for_reference(reference, other):
    """Generate a column comparison expression for a reference property.

    The returned expression may be used to find referenced objects referring
    to C{other}.

    If the right hand side is a collection of values, then an OR in IN
    expression is returned - if the relation uses composite keys, then an OR
    expression is used; single key references produce an IN expression which is
    more efficient for large collections of values.
    """
    relation = reference._relation
    if isinstance(other, (list, set, tuple,)):
        return _get_where_for_local_many(relation, other)
    else:
        return relation.get_where_for_local(other)


def _remote_variables(relation, obj):
    """A helper function to extract the foreign key values of an object.
    """
    try:
        get_obj_info(obj)
    except ClassInfoError:
        if type(obj) is not tuple:
            remote_variables = (obj,)
        else:
            remote_variables = obj
    else:
        # Don't use other here, as it might be
        # security proxied or something.
        obj = get_obj_info(obj).get_obj()
        remote_variables = relation.get_remote_variables(obj)
    return remote_variables


def _get_where_for_local_many(relation, others):
    """Generate an OR or IN expression used to find others.

    If the relation uses composite keys, then an OR expression is used;
    single key references produce an IN expression which is more efficient for
    large collections of values.
    """

    if len(relation.local_key) == 1:
        return In(
            relation.local_key[0],
            [_remote_variables(relation, value) for value in others])
    else:
        return Or(*[relation.get_where_for_local(value) for value in others])


def determine_table_and_fragment(table, ftq):
    table = get_cls_info(table).table
    if ftq:
        query_fragment = "ftq(?)"
    else:
        query_fragment = "?::tsquery"
    return table, query_fragment


def fti_search(table, text, ftq=True):
    """An expression ensuring that table rows match the specified text."""
    table, query_fragment = determine_table_and_fragment(table, ftq)
    return SQL(
        '%s.fti @@ %s' % (table.name, query_fragment), params=(text,),
        tables=(table,))


def rank_by_fti(table, text, ftq=True):
    table, query_fragment = determine_table_and_fragment(table, ftq)
    return SQL(
        '-rank(%s.fti, %s)' % (table.name, query_fragment), params=(text,),
        tables=(table,))
