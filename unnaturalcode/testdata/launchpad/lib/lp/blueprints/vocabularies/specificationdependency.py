# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The vocabularies relating to dependencies of specifications."""

__metaclass__ = type
__all__ = [
    'SpecificationDepCandidatesVocabulary',
    'SpecificationDependenciesVocabulary',
    ]

from storm.locals import (
    And,
    SQL,
    Store,
    )
from zope.component import getUtility
from zope.interface import implements
from zope.schema.vocabulary import SimpleTerm

from lp.blueprints.model.specification import (
    recursive_blocked_query,
    Specification,
    )
from lp.blueprints.model.specificationdependency import (
    SpecificationDependency,
    )
from lp.blueprints.model.specificationsearch import (
    get_specification_privacy_filter,
    )
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.services.database.stormexpr import fti_search
from lp.services.webapp import (
    canonical_url,
    urlparse,
    )
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.vocabulary import (
    CountableIterator,
    IHugeVocabulary,
    SQLObjectVocabularyBase,
    )


class SpecificationDepCandidatesVocabulary(SQLObjectVocabularyBase):
    """Specifications that could be dependencies of this spec.

    This includes only those specs that are not blocked by this spec (directly
    or indirectly), unless they are already dependencies.

    This vocabulary has a bit of a split personality.

    Tokens are *either*:

     - the name of a spec, in which case it must be a spec on the same target
       as the context, or
     - the full URL of the spec, in which case it can be any spec at all.

    For the purposes of enumeration and searching we look at all the possible
    specifications, but order those of the same target first.  If there is an
    associated series as well, then those are shown before other matches not
    linked to the same series.
    """

    implements(IHugeVocabulary)

    _table = Specification
    _orderBy = 'name'
    displayname = 'Select a blueprint'
    step_title = 'Search'

    def _is_valid_candidate(self, spec):
        """Is `spec` a valid candidate spec for self.context?

        Invalid candidates are:

         * None
         * The spec that we're adding a depdency to
         * Specs that depend on this one

        Preventing the last category prevents loops in the dependency graph.
        """
        if spec is None or spec == self.context:
            return False
        user = getattr(getUtility(ILaunchBag), 'user', None)
        return spec not in set(self.context.all_blocked(user=user))

    def _order_by(self):
        """Look at the context to provide grouping.

        If the blueprint is for a project, then matching results for that
        project should be first.  If the blueprint is set for a series, then
        that series should come before others for the project.  Similarly for
        the distribution, and the series goal for the distribution.

        If all else is equal, the ordering is by name, then database id as a
        final uniqueness resolver.
        """
        order_statements = []
        spec = self.context
        if spec.product is not None:
            order_statements.append(
                "(CASE Specification.product WHEN %s THEN 0 ELSE 1 END)" %
                spec.product.id)
            if spec.productseries is not None:
                order_statements.append(
                    "(CASE Specification.productseries"
                    " WHEN %s THEN 0 ELSE 1 END)" %
                    spec.productseries.id)
        elif spec.distribution is not None:
            order_statements.append(
                "(CASE Specification.distribution WHEN %s THEN 0 ELSE 1 END)"
                % spec.distribution.id)
            if spec.distroseries is not None:
                order_statements.append(
                    "(CASE Specification.distroseries"
                    " WHEN %s THEN 0 ELSE 1 END)" %
                    spec.distroseries.id)
        order_statements.append("Specification.name")
        order_statements.append("Specification.id")
        return SQL(', '.join(order_statements))

    def _exclude_blocked_query(self):
        """Return the select statement to exclude already blocked specs."""
        user = getattr(getUtility(ILaunchBag), 'user', None)
        return SQL(
            "Specification.id not in (WITH %s select id from blocked)" % (
                recursive_blocked_query(user)), params=(self.context.id,))

    def toTerm(self, obj):
        if obj.target == self.context.target:
            token = obj.name
        else:
            token = canonical_url(obj)
        return SimpleTerm(obj, token, obj.title)

    def _spec_from_url(self, url):
        """If `url` is the URL of a specification, return it.

        This implementation is a little fuzzy and will return specs for URLs
        that, for example, don't have the host name right.  This seems
        unlikely to cause confusion in practice, and being too anal probably
        would be confusing (e.g. not accepting production URLs on staging).
        """
        scheme, netloc, path, params, args, fragment = urlparse(url)
        if not scheme or not netloc:
            # Not enough like a URL
            return None
        path_segments = path.strip('/').split('/')
        if len(path_segments) != 3:
            # Can't be a spec url
            return None
        pillar_name, plus_spec, spec_name = path_segments
        if plus_spec != '+spec':
            # Can't be a spec url
            return None
        pillar = getUtility(IPillarNameSet).getByName(
            pillar_name, ignore_inactive=True)
        if pillar is None:
            return None
        return pillar.getSpecification(spec_name)

    def getTermByToken(self, token):
        """See `zope.schema.interfaces.IVocabularyTokenized`.

        The tokens for specifications are either the name of a spec on the
        same target or a URL for a spec.
        """
        spec = self._spec_from_url(token)
        if spec is None:
            spec = self.context.target.getSpecification(token)
        if self._is_valid_candidate(spec):
            return self.toTerm(spec)
        raise LookupError(token)

    def search(self, query, vocab_filter=None):
        """See `SQLObjectVocabularyBase.search`.

        We find specs where query is in the text of name or title, or matches
        the full text index and then filter out ineligible specs using
        `_filter_specs`.
        """
        if not query:
            return CountableIterator(0, [])
        spec = self._spec_from_url(query)
        if self._is_valid_candidate(spec):
            return CountableIterator(1, [spec])

        return Store.of(self.context).find(
            Specification,
            fti_search(Specification, query),
            self._exclude_blocked_query(),
            ).order_by(self._order_by())

    def __iter__(self):
        # We don't ever want to iterate over everything.
        raise NotImplementedError()

    def __contains__(self, obj):
        return self._is_valid_candidate(obj)


class SpecificationDependenciesVocabulary(SQLObjectVocabularyBase):
    """List specifications on which the current specification depends."""

    _table = Specification
    _orderBy = 'title'

    @property
    def _filter(self):
        user = getattr(getUtility(ILaunchBag), 'user', None)
        return And(
            SpecificationDependency.specificationID == self.context.id,
            SpecificationDependency.dependencyID == Specification.id,
            *get_specification_privacy_filter(user))
