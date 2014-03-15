# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Adapters for different objects to branch collections."""

__metaclass__ = type
__all__ = [
    'branch_collection_for_distribution',
    'branch_collection_for_distro_series',
    'branch_collection_for_person',
    'branch_collection_for_product',
    'branch_collection_for_project',
    'branch_collection_for_source_package',
    'branch_collection_for_distro_source_package',
    ]


from zope.component import getUtility

from lp.code.interfaces.branchcollection import IAllBranches


def branch_collection_for_product(product):
    """Adapt a product to a branch collection."""
    return getUtility(IAllBranches).inProduct(product)


def branch_collection_for_project(project):
    """Adapt a project to a branch collection."""
    return getUtility(IAllBranches).inProject(project)


def branch_collection_for_person(person):
    """Adapt a person to a branch collection."""
    return getUtility(IAllBranches).ownedBy(person)


def branch_collection_for_person_product(person_product):
    """Adapt a PersonProduct to a branch collection."""
    collection = getUtility(IAllBranches).ownedBy(person_product.person)
    collection = collection.inProduct(person_product.product)
    return collection


def branch_collection_for_distribution(distribution):
    """Adapt a distribution to a branch collection."""
    return getUtility(IAllBranches).inDistribution(distribution)


def branch_collection_for_distro_series(distro_series):
    """Adapt a distro_series to a branch collection."""
    return getUtility(IAllBranches).inDistroSeries(distro_series)


def branch_collection_for_source_package(source_package):
    """Adapt a source_package to a branch collection."""
    return getUtility(IAllBranches).inSourcePackage(source_package)


def branch_collection_for_distro_source_package(distro_source_package):
    """Adapt a distro_source_package to a branch collection."""
    return getUtility(IAllBranches).inDistributionSourcePackage(
        distro_source_package)
