# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = ['SpecificationDependency']

from sqlobject import ForeignKey
from zope.interface import implements

from lp.blueprints.interfaces.specificationdependency import (
    ISpecificationDependency,
    )
from lp.services.database.sqlbase import SQLBase


class SpecificationDependency(SQLBase):
    """A link between a spec and a bug."""

    implements(ISpecificationDependency)

    _table = 'SpecificationDependency'
    specification = ForeignKey(dbName='specification',
        foreignKey='Specification', notNull=True)
    dependency = ForeignKey(dbName='dependency',
        foreignKey='Specification', notNull=True)


