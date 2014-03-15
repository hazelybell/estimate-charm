# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Vocabularies pulling stuff from the database.

You probably don't want to use these classes directly - see the
docstring in __init__.py for details.
"""

__metaclass__ = type

__all__ = [
    'FilteredVocabularyBase',
    'ForgivingSimpleVocabulary',
    'IHugeVocabulary',
    'SQLObjectVocabularyBase',
    'NamedSQLObjectVocabulary',
    'NamedSQLObjectHugeVocabulary',
    'CountableIterator',
    'BatchedCountableIterator',
    'VocabularyFilter',
]

from collections import namedtuple

from lazr.restful.utils import safe_hasattr
from sqlobject import (
    AND,
    CONTAINSSTRING,
    )
from zope.interface import (
    Attribute,
    implements,
    Interface,
    )
from zope.schema.interfaces import (
    IVocabulary,
    IVocabularyTokenized,
    )
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )
from zope.security.proxy import isinstance as zisinstance

from lp.services.database.sqlbase import SQLBase
from lp.services.helpers import ensure_unicode


class ForgivingSimpleVocabulary(SimpleVocabulary):
    """A vocabulary that returns a default term for unrecognized values."""

    def __init__(self, *args, **kws):
        missing = object()
        self._default_term = kws.pop('default_term', missing)
        if self._default_term is missing:
            raise TypeError('required argument "default_term" not provided')
        return super(ForgivingSimpleVocabulary, self).__init__(*args, **kws)

    def getTerm(self, value):
        """Look up a value, returning the default if it is not found."""
        try:
            return super(ForgivingSimpleVocabulary, self).getTerm(value)
        except LookupError:
            return self._default_term


class VocabularyFilter(namedtuple('VocabularyFilter',
                                ('name', 'title', 'description'))):
    """A VocabularyFilter is used to filter the results of searchForTerms()

    A filter has the following attributes:
    name: the filter name, eg ALL, PRODUCT
    title: the text displayed in the ui, as presented to the user eg 'All'
    description: the tooltip text
    """

    @property
    def filter_terms(self):
        """Query terms used to perform the required filtering."""
        return []


class IHugeVocabulary(IVocabulary, IVocabularyTokenized):
    """Interface for huge vocabularies.

    Items in an IHugeVocabulary should have human readable tokens or the
    default UI will suck.
    """

    displayname = Attribute(
        'A name for this vocabulary, to be displayed in the picker window.')

    step_title = Attribute(
        'The search step title in the picker window.')

    def searchForTerms(query=None, vocab_filter=None):
        """Return a `CountableIterator` of `SimpleTerm`s that match the query.

        :param query: a query string used to limit the results.
        :param vocab_filter: a VocabularyFilter applied to the results. A
            filter has a specific meaning for each vocabulary implementation
            which supports it's use. Vocabularies which support the use of
            filters should each accept the ALL filter which means the same as
            not applying any filter.
            The parameter value can be a string corresponding to a supported
            filter name, or a filter instance.

        Note that what is searched and how the match is the choice of the
        IHugeVocabulary implementation.
        """

    def supportedFilters():
        """Return the VocabularyFilters supported by searchForTerms.
        """


class ICountableIterator(Interface):
    """An iterator that knows how many items it has."""

    # XXX: JonathanLange 2009-02-23: This should probably be fused with or at
    # least adapted from storm.zope.interfaces.IResultSet. Or maybe just
    # deleted in favour of passing around Storm ResultSets.
    def count():
        """Return the number of items in the iterator."""

    def __iter__():
        """Iterate over items."""

    def __getitem__(argument):
        """Return a slice or item of the collection."""

    def __len__():
        """Synonym for `ICountableIterator.count`."""
        # XXX kiko 2007-01-16: __len__ is required to make BatchNavigator
        # work; we should probably change that to either check for the
        # presence of a count() method, or for a simpler interface than
        # ISelectResults, but I'm not going to do that today.
        pass

    def __getslice__(argument):
        """Return a slice of the collection."""
        # Python will use __getitem__ if this method is not implemented,
        # but it is convenient to define it in the interface for
        # allowing access to the attributes through the security proxy.
        pass


class CountableIterator:
    """Implements a wrapping iterator with a count() method.

    This iterator implements a subset of the ISelectResults interface;
    namely the portion required to have it work as part of a
    BatchNavigator.
    """

    implements(ICountableIterator)

    def __init__(self, count, iterator, item_wrapper=None):
        """Construct a CountableIterator instance.

        Arguments:
            - count: number of items in the iterator
            - iterator: the iterable we wrap; normally a ISelectResults
            - item_wrapper: a callable that will be invoked for each
              item we return.
        """
        self._count = count
        self._iterator = iterator
        self._item_wrapper = item_wrapper

    def count(self):
        """Return the number of items in the iterator."""
        return self._count

    def __iter__(self):
        """Iterate over my items.

        This is used when building the <select> menu of options that is
        generated when we post a form.
        """
        # XXX kiko 2007-01-18: We can actually raise an AssertionError here
        # because we shouldn't need to iterate over all the results, ever;
        # this is currently here because popup.py:matches() doesn't slice
        # into the results, though it should.
        for item in self._iterator:
            if self._item_wrapper is not None:
                yield self._item_wrapper(item)
            else:
                yield item

    def __getitem__(self, arg):
        """Return a slice or item of my collection.

        This is used by BatchNavigator when it slices into us; we just
        pass on the buck down to our _iterator."""
        for item in self._iterator[arg]:
            if self._item_wrapper is not None:
                yield self._item_wrapper(item)
            else:
                yield item

    def __len__(self):
        return self._count


class BatchedCountableIterator(CountableIterator):
    """A wrapping iterator with hook to create descriptions for its terms."""
    # XXX kiko 2007-01-18: note that this class doesn't use the item_wrapper
    # at all. I hate compatibility shims. We can't remove it from the __init__
    # because it is always supplied by NamedSQLObjectHugeVocabulary, and
    # we don't want child classes to have to reimplement it.  This
    # probably indicates we need to reconsider how these classes are
    # split.
    def __iter__(self):
        """See CountableIterator"""
        return iter(self.getTermsWithDescriptions(self._iterator))

    def __getitem__(self, arg):
        """See CountableIterator"""
        item = self._iterator[arg]
        if isinstance(arg, slice):
            return self.getTermsWithDescriptions(item)
        else:
            return self.getTermsWithDescriptions([item])[0]

    def getTermsWithDescriptions(self, results):
        """Return SimpleTerms with their titles properly fabricated.

        This is a hook method that allows subclasses to implement their
        own [complex] calculations for what the term's title might be.
        It takes an iterable set of results based on that searchForTerms
        of the corresponding vocabulary does.
        """
        raise NotImplementedError


class VocabularyFilterAll(VocabularyFilter):
    # A filter returning all objects.

    def __new__(cls):
        return super(VocabularyFilter, cls).__new__(
            cls, 'ALL', 'All', 'Display all search results')


class FilteredVocabularyBase:
    """A mixin to provide base filtering support."""

    ALL_FILTER = VocabularyFilterAll()

    # We need to convert any string values passed in for the vocab_filter
    # parameter to a VocabularyFilter instance.
    def __getattribute__(self, name):
        func = object.__getattribute__(self, name)
        if (safe_hasattr(func, '__call__')
                and (
                    func.__name__ == 'searchForTerms'
                    or func.__name__ == 'search')):
            def do_search(
                    query=None, vocab_filter=None, *args, **kwargs):
                if isinstance(vocab_filter, basestring):
                    for filter in self.supportedFilters():
                        if filter.name == vocab_filter:
                            vocab_filter = filter
                            break
                    else:
                        raise ValueError(
                            "Invalid vocab filter value: %s" % vocab_filter)
                return func(query, vocab_filter, *args, **kwargs)
            return do_search
        else:
            return func

    def supportedFilters(self):
        return []


class SQLObjectVocabularyBase(FilteredVocabularyBase):
    """A base class for widgets that are rendered to collect values
    for attributes that are SQLObjects, e.g. ForeignKey.

    So if a content class behind some form looks like:

    class Foo(SQLObject):
        id = IntCol(...)
        bar = ForeignKey(...)
        ...

    Then the vocabulary for the widget that captures a value for bar
    should derive from SQLObjectVocabularyBase.
    """
    implements(IVocabulary, IVocabularyTokenized)
    _orderBy = None
    _filter = None
    _clauseTables = None

    def __init__(self, context=None):
        self.context = context

    # XXX kiko 2007-01-16: note that the method searchForTerms is part of
    # IHugeVocabulary, and so should not necessarily need to be
    # implemented here; however, many of our vocabularies depend on
    # searchForTerms for popup functionality so I have chosen to just do
    # that. It is possible that a better solution would be to have the
    # search functionality produce a new vocabulary restricted to the
    # desired subset.
    def searchForTerms(self, query=None, vocab_filter=None):
        results = self.search(query, vocab_filter)
        return CountableIterator(results.count(), results, self.toTerm)

    def search(self, query, vocab_filter=None):
        # This default implementation of searchForTerms glues together
        # the legacy API of search() with the toTerm method. If you
        # don't reimplement searchForTerms you will need to at least
        # provide your own search() method.
        raise NotImplementedError

    def toTerm(self, obj):
        # This default implementation assumes that your object has a
        # title attribute. If it does not you will need to reimplement
        # toTerm, or reimplement the whole searchForTerms.
        return SimpleTerm(obj, obj.id, obj.title)

    def __iter__(self):
        """Return an iterator which provides the terms from the vocabulary."""
        params = {}
        if self._orderBy is not None:
            params['orderBy'] = self._orderBy
        if self._clauseTables is not None:
            params['clauseTables'] = self._clauseTables
        for obj in self._table.select(self._filter, **params):
            yield self.toTerm(obj)

    def __len__(self):
        return len(list(iter(self)))

    def __contains__(self, obj):
        # Sometimes this method is called with an SQLBase instance, but
        # z3 form machinery sends through integer ids. This might be due
        # to a bug somewhere.
        if zisinstance(obj, SQLBase):
            clause = self._table.q.id == obj.id
            if self._filter:
                # XXX kiko 2007-01-16: this code is untested.
                clause = AND(clause, self._filter)
            found_obj = self._table.selectOne(clause)
            return found_obj is not None and found_obj == obj
        else:
            clause = self._table.q.id == int(obj)
            if self._filter:
                # XXX kiko 2007-01-16: this code is untested.
                clause = AND(clause, self._filter)
            found_obj = self._table.selectOne(clause)
            return found_obj is not None

    def getTerm(self, value):
        # Short circuit. There is probably a design problem here since
        # we sometimes get the id and sometimes an SQLBase instance.
        if zisinstance(value, SQLBase):
            return self.toTerm(value)

        try:
            value = int(value)
        except ValueError:
            raise LookupError(value)

        clause = self._table.q.id == value
        if self._filter:
            clause = AND(clause, self._filter)
        try:
            obj = self._table.selectOne(clause)
        except ValueError:
            raise LookupError(value)

        if obj is None:
            raise LookupError(value)

        return self.toTerm(obj)

    def getTermByToken(self, token):
        return self.getTerm(token)

    def emptySelectResults(self):
        """Return a SelectResults object without any elements.

        This is to be used when no search string is given to the search()
        method of subclasses, in order to be consistent and always return
        a SelectResults object.
        """
        return self._table.select('1 = 2')


class NamedSQLObjectVocabulary(SQLObjectVocabularyBase):
    """A SQLObjectVocabulary base for database tables that have a unique
    *and* ASCII name column.

    Provides all methods required by IHugeVocabulary, although it
    doesn't actually specify this interface since it may not actually
    be huge and require the custom widgets.
    """
    _orderBy = 'name'

    def toTerm(self, obj):
        """See SQLObjectVocabularyBase.

        This implementation uses name as a token instead of the object's
        ID, and tries to be smart about deciding to present an object's
        title if it has one.
        """
        if getattr(obj, "title", None) is None:
            return SimpleTerm(obj, obj.name, obj.name)
        else:
            return SimpleTerm(obj, obj.name, obj.title)

    def getTermByToken(self, token):
        clause = self._table.q.name == token
        if self._filter:
            clause = AND(clause, self._filter)
        objs = list(self._table.select(clause))
        if not objs:
            raise LookupError(token)
        return self.toTerm(objs[0])

    def search(self, query, vocab_filter=None):
        """Return terms where query is a subtring of the name."""
        if query:
            clause = CONTAINSSTRING(self._table.q.name, ensure_unicode(query))
            if self._filter:
                clause = AND(clause, self._filter)
            return self._table.select(clause, orderBy=self._orderBy)
        return self.emptySelectResults()


class NamedSQLObjectHugeVocabulary(NamedSQLObjectVocabulary):
    """A NamedSQLObjectVocabulary that implements IHugeVocabulary."""

    implements(IHugeVocabulary)
    _orderBy = 'name'
    displayname = None
    step_title = 'Search'
    # The iterator class will be used to wrap the results; its iteration
    # methods should return SimpleTerms, as the reference implementation
    # CountableIterator does.
    iterator = CountableIterator

    def __init__(self, context=None):
        NamedSQLObjectVocabulary.__init__(self, context)
        if self.displayname is None:
            self.displayname = 'Select %s' % self.__class__.__name__

    def search(self, query, vocab_filter=None):
        # XXX kiko 2007-01-17: this is a transitional shim; we're going to
        # get rid of search() altogether, but for now we've only done it for
        # the NamedSQLObjectHugeVocabulary.
        raise NotImplementedError

    def searchForTerms(self, query=None, vocab_filter=None):
        if not query:
            return self.emptySelectResults()

        query = ensure_unicode(query).lower()
        clause = CONTAINSSTRING(self._table.q.name, query)
        if self._filter:
            clause = AND(clause, self._filter)
        results = self._table.select(clause, orderBy=self._orderBy)
        return self.iterator(results.count(), results, self.toTerm)
