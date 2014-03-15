# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The vocabularies relating to sprints."""

__metaclass__ = type
__all__ = [
    'FutureSprintVocabulary',
    'SprintVocabulary',
    ]


from lp.blueprints.model.sprint import Sprint
from lp.services.webapp.vocabulary import NamedSQLObjectVocabulary


class FutureSprintVocabulary(NamedSQLObjectVocabulary):
    """A vocab of all sprints that have not yet finished."""

    _table = Sprint

    def __iter__(self):
        future_sprints = Sprint.select("time_ends > 'NOW'")
        for sprint in future_sprints:
            yield(self.toTerm(sprint))


class SprintVocabulary(NamedSQLObjectVocabulary):
    _table = Sprint
