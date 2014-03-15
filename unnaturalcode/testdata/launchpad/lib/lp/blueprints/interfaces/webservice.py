# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""All the interfaces that are exposed through the webservice.

There is a declaration in ZCML somewhere that looks like:
  <webservice:register module="lp.blueprints.interfaces.webservice" />

which tells `lazr.restful` that it should look for webservice exports here.
"""

__all__ = [
    'GoalProposeError',
    'ISpecification',
    'ISpecificationBranch',
    'ISpecificationSubscription',
    ]

# XXX: JonathanLange 2010-11-09 bug=673083: Legacy work-around for circular
# import bugs.  Break this up into a per-package thing.
from lp import _schema_circular_imports
from lp.blueprints.interfaces.specification import (
    GoalProposeError,
    ISpecification,
    )
from lp.blueprints.interfaces.specificationbranch import ISpecificationBranch
from lp.blueprints.interfaces.specificationsubscription import (
    ISpecificationSubscription,
    )
from lp.blueprints.interfaces.specificationtarget import ISpecificationTarget


_schema_circular_imports
