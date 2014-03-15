# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Adapters for different objects to a revision cache."""

__metaclass__ = type
__all__ = [
    'revision_cache_for_distribution',
    'revision_cache_for_distro_series',
    'revision_cache_for_person',
    'revision_cache_for_product',
    'revision_cache_for_project',
    'revision_cache_for_source_package',
    'revision_cache_for_distro_source_package',
    ]


from zope.component import getUtility

from lp.code.interfaces.revisioncache import IRevisionCache


def revision_cache_for_product(product):
    """Adapt a product to a revision cache."""
    return getUtility(IRevisionCache).inProduct(product)


def revision_cache_for_project(project):
    """Adapt a project to a revision cache."""
    return getUtility(IRevisionCache).inProject(project)


def revision_cache_for_person(person):
    """Adapt a person to a revision cache."""
    return getUtility(IRevisionCache).authoredBy(person)


def revision_cache_for_distribution(distribution):
    """Adapt a distribution to a revision cache."""
    return getUtility(IRevisionCache).inDistribution(distribution)


def revision_cache_for_distro_series(distro_series):
    """Adapt a distro_series to a revision cache."""
    return getUtility(IRevisionCache).inDistroSeries(distro_series)


def revision_cache_for_source_package(source_package):
    """Adapt a source_package to a revision cache."""
    return getUtility(IRevisionCache).inSourcePackage(source_package)


def revision_cache_for_distro_source_package(distro_source_package):
    """Adapt a distro_source_package to a revision cache."""
    return getUtility(IRevisionCache).inDistributionSourcePackage(
        distro_source_package)
