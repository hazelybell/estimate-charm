# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The vocabularies relating to specifications."""

__metaclass__ = type
__all__ = [
    'SpecificationVocabulary',
    ]

from operator import attrgetter

from zope.component import getUtility
from zope.schema.vocabulary import SimpleTerm

from lp.blueprints.model.specification import Specification
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.vocabulary import NamedSQLObjectVocabulary


class SpecificationVocabulary(NamedSQLObjectVocabulary):
    """List specifications for the current product or distribution in
    ILaunchBag, EXCEPT for the current spec in LaunchBag if one exists.
    """

    _table = Specification
    _orderBy = 'title'

    def __iter__(self):
        launchbag = getUtility(ILaunchBag)
        target = None
        product = launchbag.product
        if product is not None:
            target = product

        distribution = launchbag.distribution
        if distribution is not None:
            target = distribution

        if target is not None:
            for spec in sorted(
                target.specifications(launchbag.user),
                key=attrgetter('title')):
                # we will not show the current specification in the
                # launchbag
                if spec == launchbag.specification:
                    continue
                # we will not show a specification that is blocked on the
                # current specification in the launchbag. this is because
                # the widget is currently used to select new dependencies,
                # and we do not want to introduce circular dependencies.
                if launchbag.specification is not None:
                    user = getattr(launchbag, 'user', None)
                    if spec in launchbag.specification.all_blocked(user=user):
                        continue
                yield SimpleTerm(spec, spec.name, spec.title)
