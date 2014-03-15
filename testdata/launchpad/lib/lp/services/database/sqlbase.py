# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'block_implicit_flushes',
    'clear_current_connection_cache',
    'connect',
    'convert_storm_clause_to_string',
    'cursor',
    'flush_database_caches',
    'flush_database_updates',
    'get_transaction_timestamp',
    'ISOLATION_LEVEL_AUTOCOMMIT',
    'ISOLATION_LEVEL_DEFAULT',
    'ISOLATION_LEVEL_READ_COMMITTED',
    'ISOLATION_LEVEL_REPEATABLE_READ',
    'ISOLATION_LEVEL_SERIALIZABLE',
    'quote',
    'quote_like',
    'quoteIdentifier',
    'quote_identifier',
    'reset_store',
    'session_store',
    'SQLBase',
    'sqlvalues',
    'StupidCache',
    ]


from datetime import datetime

import psycopg2
from psycopg2.extensions import (
    ISOLATION_LEVEL_AUTOCOMMIT,
    ISOLATION_LEVEL_READ_COMMITTED,
    ISOLATION_LEVEL_REPEATABLE_READ,
    ISOLATION_LEVEL_SERIALIZABLE,
    )
import pytz
from sqlobject.sqlbuilder import sqlrepr
import storm
from storm.databases.postgres import compile as postgres_compile
from storm.expr import (
    compile as storm_compile,
    State,
    )
from storm.locals import (
    Store,
    Storm,
    )
from storm.zope.interfaces import IZStorm
from twisted.python.util import mergeFunctionMetadata
from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.services.config import dbconfig
from lp.services.database.interfaces import (
    DEFAULT_FLAVOR,
    DisallowedStore,
    IMasterObject,
    IMasterStore,
    ISQLBase,
    IStore,
    IStoreSelector,
    MAIN_STORE,
    )
from lp.services.propertycache import clear_property_cache

# Default we want for scripts, and the PostgreSQL default. Note psycopg1 will
# use SERIALIZABLE unless we override, but psycopg2 will not.
ISOLATION_LEVEL_DEFAULT = ISOLATION_LEVEL_READ_COMMITTED


# XXX 20080313 jamesh:
# When quoting names in SQL statements, PostgreSQL treats them as case
# sensitive.  Storm includes a list of reserved words that it
# automatically quotes, which includes a few of our table names.  We
# remove them here due to case mismatches between the DB and Launchpad
# code.
postgres_compile.remove_reserved_words(['language', 'section'])


class StupidCache:
    """A Storm cache that never evicts objects except on clear().

    This class is basically equivalent to Storm's standard Cache class
    with a very large size but without the overhead of maintaining the
    LRU list.

    This provides caching behaviour equivalent to what we were using
    under SQLObject.
    """

    def __init__(self, size):
        self._cache = {}

    def clear(self):
        self._cache.clear()

    def add(self, obj_info):
        if obj_info not in self._cache:
            self._cache[obj_info] = obj_info.get_obj()

    def remove(self, obj_info):
        if obj_info in self._cache:
            del self._cache[obj_info]
            return True
        return False

    def set_size(self, size):
        pass

    def get_cached(self):
        return self._cache.keys()


def _get_sqlobject_store():
    """Return the store used by the SQLObject compatibility layer."""
    return getUtility(IStoreSelector).get(MAIN_STORE, DEFAULT_FLAVOR)


class LaunchpadStyle(storm.sqlobject.SQLObjectStyle):
    """A SQLObject style for launchpad.

    Python attributes and database columns are lowercase.
    Class names and database tables are MixedCase. Using this style should
    simplify SQLBase class definitions since more defaults will be correct.
    """

    def pythonAttrToDBColumn(self, attr):
        return attr

    def dbColumnToPythonAttr(self, col):
        return col

    def pythonClassToDBTable(self, className):
        return className

    def dbTableToPythonClass(self, table):
        return table

    def idForTable(self, table):
        return 'id'

    def pythonClassToAttr(self, className):
        return className.lower()

    # dsilvers: 20050322: If you take this method out; then RelativeJoin
    # instances in our SQLObject classes cause the following error:
    # AttributeError: 'LaunchpadStyle' object has no attribute
    # 'tableReference'
    def tableReference(self, table):
        """Return the tablename mapped for use in RelativeJoin statements."""
        return table.__str__()


class SQLBase(storm.sqlobject.SQLObjectBase):
    """Base class emulating SQLObject for legacy database classes.
    """
    implements(ISQLBase)
    _style = LaunchpadStyle()

    # Silence warnings in linter script, which complains about all
    # SQLBase-derived objects missing an id.
    id = None

    def __init__(self, *args, **kwargs):
        """Extended version of the SQLObjectBase constructor.

        We force use of the master Store.

        We refetch any parameters from different stores from the
        correct master Store.
        """
        # Make it simple to write dumb-invalidators - initialized
        # _cached_properties to a valid list rather than just-in-time
        # creation.
        self._cached_properties = []
        store = IMasterStore(self.__class__)

        # The constructor will fail if objects from a different Store
        # are passed in. We need to refetch these objects from the correct
        # master Store if necessary so the foreign key references can be
        # constructed.
        # XXX StuartBishop 2009-03-02 bug=336867: We probably want to remove
        # this code - there are enough other places developers have to be
        # aware of the replication # set boundaries. Why should
        # Person(..., account=an_account) work but
        # some_person.account = an_account fail?
        for key, argument in kwargs.items():
            argument = removeSecurityProxy(argument)
            if not isinstance(argument, Storm):
                continue
            argument_store = Store.of(argument)
            if argument_store is not store:
                new_argument = store.find(
                    argument.__class__, id=argument.id).one()
                assert new_argument is not None, (
                    '%s not yet synced to this store' % repr(argument))
                kwargs[key] = new_argument

        store.add(self)
        try:
            self._create(None, **kwargs)
        except:
            store.remove(self)
            raise

    @classmethod
    def _get_store(cls):
        return IStore(cls)

    def __repr__(self):
        # XXX jamesh 2008-05-09:
        # This matches the repr() output for the sqlos.SQLOS class.
        # A number of the doctests rely on this formatting.
        return '<%s at 0x%x>' % (self.__class__.__name__, id(self))

    def destroySelf(self):
        my_master = IMasterObject(self)
        if self is my_master:
            super(SQLBase, self).destroySelf()
        else:
            my_master.destroySelf()

    def __eq__(self, other):
        """Equality operator.

        Objects compare equal if:
            - They are the same instance, or
            - They have the same class and id, and the id is not None.

        These rules allows objects retrieved from different stores to
        compare equal. The 'is' comparison is to support newly created
        objects that don't yet have an id (and by definition only exist
        in the Master store).
        """
        naked_self = removeSecurityProxy(self)
        naked_other = removeSecurityProxy(other)
        return (
            (naked_self is naked_other)
            or (naked_self.__class__ == naked_other.__class__
                and naked_self.id is not None
                and naked_self.id == naked_other.id))

    def __ne__(self, other):
        """Inverse of __eq__."""
        return not (self == other)

    def __storm_invalidated__(self):
        """Flush cached properties."""
        # XXX: RobertCollins 2010-08-16 bug=622648: Note this is not directly
        # tested, but the entire test suite blows up awesomely if it's broken.
        # It's entirely unclear where tests for this should be.
        clear_property_cache(self)


def clear_current_connection_cache():
    """Clear SQLObject's object cache. SQLObject compatibility - DEPRECATED.
    """
    _get_sqlobject_store().invalidate()


def get_transaction_timestamp():
    """Get the timestamp for the current transaction on the MAIN DEFAULT
    store. DEPRECATED - if needed it should become a method on the store.
    """
    timestamp = _get_sqlobject_store().execute(
        "SELECT CURRENT_TIMESTAMP AT TIME ZONE 'UTC'").get_one()[0]
    return timestamp.replace(tzinfo=pytz.timezone('UTC'))


def quote(x):
    r"""Quote a variable ready for inclusion into an SQL statement.
    Note that you should use quote_like to create a LIKE comparison.

    Basic SQL quoting works

    >>> quote(1)
    '1'
    >>> quote(1.0)
    '1.0'
    >>> quote("hello")
    "'hello'"
    >>> quote("'hello'")
    "'''hello'''"
    >>> quote(r"\'hello")
    "'\\\\''hello'"

    Note that we need to receive a Unicode string back, because our
    query will be a Unicode string (the entire query will be encoded
    before sending across the wire to the database).

    >>> quote(u"\N{TRADE MARK SIGN}")
    u"'\u2122'"

    Timezone handling is not implemented, since all timestamps should
    be UTC anyway.

    >>> from datetime import datetime, date, time
    >>> quote(datetime(2003, 12, 4, 13, 45, 50))
    "'2003-12-04 13:45:50'"
    >>> quote(date(2003, 12, 4))
    "'2003-12-04'"
    >>> quote(time(13, 45, 50))
    "'13:45:50'"

    This function special cases datetime objects, due to a bug that has
    since been fixed in SQLOS (it installed an SQLObject converter that
    stripped the time component from the value).  By itself, the sqlrepr
    function has the following output:

    >>> sqlrepr(datetime(2003, 12, 4, 13, 45, 50), 'postgres')
    "'2003-12-04T13:45:50'"

    This function also special cases set objects, which SQLObject's
    sqlrepr() doesn't know how to handle.

    >>> quote(set([1,2,3]))
    '(1, 2, 3)'

    >>> quote(frozenset([1,2,3]))
    '(1, 2, 3)'
    """
    if isinstance(x, datetime):
        return "'%s'" % x
    elif ISQLBase(x, None) is not None:
        return str(x.id)
    elif isinstance(x, (set, frozenset)):
        # SQLObject can't cope with sets, so convert to a list, which it
        # /does/ know how to handle.
        x = list(x)
    return sqlrepr(x, 'postgres')


def quote_like(x):
    r"""Quote a variable ready for inclusion in a SQL statement's LIKE clause

    XXX: StuartBishop 2004-11-24:
    Including the single quotes was a stupid decision.

    To correctly generate a SELECT using a LIKE comparision, we need
    to make use of the SQL string concatination operator '||' and the
    quote_like method to ensure that any characters with special meaning
    to the LIKE operator are correctly escaped.

    >>> "SELECT * FROM mytable WHERE mycol LIKE '%%' || %s || '%%'" \
    ...     % quote_like('%')
    "SELECT * FROM mytable WHERE mycol LIKE '%' || '\\\\%' || '%'"

    Note that we need 2 backslashes to quote, as per the docs on
    the LIKE operator. This is because, unless overridden, the LIKE
    operator uses the same escape character as the SQL parser.

    >>> quote_like('100%')
    "'100\\\\%'"
    >>> quote_like('foobar_alpha1')
    "'foobar\\\\_alpha1'"
    >>> quote_like('hello')
    "'hello'"

    Only strings are supported by this method.

    >>> quote_like(1)
    Traceback (most recent call last):
        [...]
    TypeError: Not a string (<type 'int'>)

    """
    if not isinstance(x, basestring):
        raise TypeError('Not a string (%s)' % type(x))
    return quote(x).replace('%', r'\\%').replace('_', r'\\_')


def sqlvalues(*values, **kwvalues):
    """Return a tuple of converted sql values for each value in some_tuple.

    This safely quotes strings, or gives representations of dbschema items,
    for example.

    Use it when constructing a string for use in a SELECT.  Always use
    %s as the replacement marker.

      ('SELECT foo from Foo where bar = %s and baz = %s'
       % sqlvalues(BugTaskSeverity.CRITICAL, 'foo'))

    >>> sqlvalues()
    Traceback (most recent call last):
    ...
    TypeError: Use either positional or keyword values with sqlvalue.
    >>> sqlvalues(1)
    ('1',)
    >>> sqlvalues(1, "bad ' string")
    ('1', "'bad '' string'")

    You can also use it when using dict-style substitution.

    >>> sqlvalues(foo=23)
    {'foo': '23'}

    However, you cannot mix the styles.

    >>> sqlvalues(14, foo=23)
    Traceback (most recent call last):
    ...
    TypeError: Use either positional or keyword values with sqlvalue.

    """
    if (values and kwvalues) or (not values and not kwvalues):
        raise TypeError(
            "Use either positional or keyword values with sqlvalue.")
    if values:
        return tuple(quote(item) for item in values)
    elif kwvalues:
        return dict((key, quote(value)) for key, value in kwvalues.items())


def quote_identifier(identifier):
    r'''Quote an identifier, such as a table name.

    In SQL, identifiers are quoted using " rather than ' which is reserved
    for strings.

    >>> print quoteIdentifier('hello')
    "hello"
    >>> print quoteIdentifier("'")
    "'"
    >>> print quoteIdentifier('"')
    """"
    >>> print quoteIdentifier("\\")
    "\"
    >>> print quoteIdentifier('\\"')
    "\"""
    '''
    return '"%s"' % identifier.replace('"', '""')


quoteIdentifier = quote_identifier  # Backwards compatibility for now.


def convert_storm_clause_to_string(storm_clause):
    """Convert a Storm expression into a plain string.

    :param storm_clause: A Storm expression

    A helper function allowing to use a Storm expressions in old-style
    code which builds for example WHERE expressions as plain strings.

    >>> from lp.bugs.model.bug import Bug
    >>> from lp.bugs.model.bugtask import BugTask
    >>> from lp.bugs.interfaces.bugtask import BugTaskImportance
    >>> from storm.expr import And, Or

    >>> print convert_storm_clause_to_string(BugTask)
    BugTask

    >>> print convert_storm_clause_to_string(BugTask.id == 16)
    BugTask.id = 16

    >>> print convert_storm_clause_to_string(
    ...     BugTask.importance == BugTaskImportance.UNKNOWN)
    BugTask.importance = 999

    >>> print convert_storm_clause_to_string(Bug.title == "foo'bar'")
    Bug.title = 'foo''bar'''

    >>> print convert_storm_clause_to_string(
    ...     Or(BugTask.importance == BugTaskImportance.UNKNOWN,
    ...        BugTask.importance == BugTaskImportance.HIGH))
    BugTask.importance = 999 OR BugTask.importance = 40

    >>> print convert_storm_clause_to_string(
    ...    And(Bug.title == 'foo', BugTask.bug == Bug.id,
    ...        Or(BugTask.importance == BugTaskImportance.UNKNOWN,
    ...           BugTask.importance == BugTaskImportance.HIGH)))
    Bug.title = 'foo' AND BugTask.bug = Bug.id AND
    (BugTask.importance = 999 OR BugTask.importance = 40)
    """
    state = State()
    clause = storm_compile(storm_clause, state)
    if len(state.parameters):
        parameters = [param.get(to_db=True) for param in state.parameters]
        clause = clause.replace('?', '%s') % sqlvalues(*parameters)
    return clause


def flush_database_updates():
    """Flushes all pending database updates.

    When SQLObject's _lazyUpdate flag is set, then it's possible to have
    changes written to objects that aren't flushed to the database, leading to
    inconsistencies when doing e.g.::

        # Assuming the Beer table already has a 'Victoria Bitter' row...
        assert Beer.select("name LIKE 'Vic%'").count() == 1  # This will pass
        beer = Beer.byName('Victoria Bitter')
        beer.name = 'VB'
        assert Beer.select("name LIKE 'Vic%'").count() == 0  # This will fail

    To avoid this problem, use this function::

        # Assuming the Beer table already has a 'Victoria Bitter' row...
        assert Beer.select("name LIKE 'Vic%'").count() == 1  # This will pass
        beer = Beer.byName('Victoria Bitter')
        beer.name = 'VB'
        flush_database_updates()
        assert Beer.select("name LIKE 'Vic%'").count() == 0  # This will pass

    """
    zstorm = getUtility(IZStorm)
    for name, store in zstorm.iterstores():
        store.flush()


def flush_database_caches():
    """Flush all database caches.

    SQLObject caches field values from the database in SQLObject
    instances.  If SQL statements are issued that change the state of
    the database behind SQLObject's back, these cached values will be
    invalid.

    This function iterates through all the objects in the SQLObject
    connection's cache, and synchronises them with the database.  This
    ensures that they all reflect the values in the database.
    """
    zstorm = getUtility(IZStorm)
    for name, store in zstorm.iterstores():
        store.flush()
        store.invalidate()


def block_implicit_flushes(func):
    """A decorator that blocks implicit flushes on the main store."""

    def block_implicit_flushes_decorator(*args, **kwargs):
        try:
            store = _get_sqlobject_store()
        except DisallowedStore:
            return func(*args, **kwargs)
        store.block_implicit_flushes()
        try:
            return func(*args, **kwargs)
        finally:
            store.unblock_implicit_flushes()
    return mergeFunctionMetadata(func, block_implicit_flushes_decorator)


def reset_store(func):
    """Function decorator that resets the main store."""

    def reset_store_decorator(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            _get_sqlobject_store().reset()
    return mergeFunctionMetadata(func, reset_store_decorator)


def connect(user=None, dbname=None, isolation=ISOLATION_LEVEL_DEFAULT):
    """Return a fresh DB-API connection to the MAIN MASTER database.

    Can be used without first setting up the Component Architecture,
    unlike the usual stores.

    Default database name is the one specified in the main configuration file.
    """
    con = psycopg2.connect(connect_string(user=user, dbname=dbname))
    con.set_isolation_level(isolation)
    return con


def connect_string(user=None, dbname=None):
    """Return a PostgreSQL connection string.

    Allows you to pass the generated connection details to external
    programs like pg_dump or embed in slonik scripts.
    """
    # We must connect to the read-write DB here, so we use rw_main_master
    # directly.
    from lp.services.database.postgresql import ConnectionString
    con_str = ConnectionString(dbconfig.rw_main_master)
    if user is not None:
        con_str.user = user
    if dbname is not None:
        con_str.dbname = dbname
    return str(con_str)


class cursor:
    """A DB-API cursor-like object for the Storm connection.

    DEPRECATED - use of this class is deprecated in favour of using
    Store.execute().
    """

    def __init__(self):
        self._connection = _get_sqlobject_store()._connection
        self._result = None

    def execute(self, query, params=None):
        self.close()
        if isinstance(params, dict):
            query = query % sqlvalues(**params)
        elif params is not None:
            query = query % sqlvalues(*params)
        self._result = self._connection.execute(query)

    @property
    def rowcount(self):
        return self._result._raw_cursor.rowcount

    @property
    def description(self):
        return self._result._raw_cursor.description

    def fetchone(self):
        assert self._result is not None, "No results to fetch"
        return self._result.get_one()

    def fetchall(self):
        assert self._result is not None, "No results to fetch"
        return self._result.get_all()

    def close(self):
        if self._result is not None:
            self._result.close()
            self._result = None


def session_store():
    """Return a store connected to the session DB."""
    return getUtility(IZStorm).get('session', 'launchpad-session:')
