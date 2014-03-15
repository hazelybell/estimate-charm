# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from storm.locals import (
    Bool,
    DateTime,
    Int,
    List,
    Reference,
    Storm,
    )

from lp.app.enums import InformationType
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    BugTaskStatusSearch,
    )
from lp.services.database.enumcol import EnumCol


class BugTaskFlat(Storm):

    __storm_table__ = 'BugTaskFlat'

    bugtask_id = Int(name='bugtask', primary=True)
    bugtask = Reference(bugtask_id, 'BugTask.id')
    bug_id = Int(name='bug')
    bug = Reference(bug_id, 'Bug.id')
    datecreated = DateTime()
    latest_patch_uploaded = DateTime()
    date_closed = DateTime()
    date_last_updated = DateTime()
    duplicateof_id = Int(name='duplicateof')
    duplicateof = Reference(duplicateof_id, 'Bug.id')
    bug_owner_id = Int(name='bug_owner')
    bug_owner = Reference(bug_owner_id, 'Person.id')
    information_type = EnumCol(enum=InformationType)
    heat = Int()
    product_id = Int(name='product')
    product = Reference(product_id, 'Product.id')
    productseries_id = Int(name='productseries')
    productseries = Reference(productseries_id, 'ProductSeries.id')
    distribution_id = Int(name='distribution')
    distribution = Reference(distribution_id, 'Distribution.id')
    distroseries_id = Int(name='distroseries')
    distroseries = Reference(distroseries_id, 'DistroSeries.id')
    sourcepackagename_id = Int(name='sourcepackagename')
    sourcepackagename = Reference(
        sourcepackagename_id, 'SourcePackageName.id')
    status = EnumCol(schema=(BugTaskStatus, BugTaskStatusSearch))
    importance = EnumCol(schema=BugTaskImportance)
    assignee_id = Int(name='assignee')
    assignee = Reference(assignee_id, 'Person.id')
    milestone_id = Int(name='milestone')
    milestone = Reference(milestone_id, 'Milestone.id')
    owner_id = Int(name='owner')
    owner = Reference(owner_id, 'Person.id')
    active = Bool()
    access_grants = List(type=Int())
    access_policies = List(type=Int())
