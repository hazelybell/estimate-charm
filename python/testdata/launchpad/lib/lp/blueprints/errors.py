# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Specification views."""

__metaclass__ = type

__all__ = [
    'TargetAlreadyHasSpecification',
    ]


class TargetAlreadyHasSpecification(Exception):
    """The ISpecificationTarget already has a specification of that name."""

    def __init__(self, target, name):
        msg = "The target %s already has a specification named %s" % (
                target, name)
        super(TargetAlreadyHasSpecification, self).__init__(msg)
