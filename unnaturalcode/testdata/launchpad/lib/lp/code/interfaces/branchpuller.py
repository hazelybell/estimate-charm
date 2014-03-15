# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The public interface to the model of the branch puller."""

__metaclass__ = type
__all__ = [
    'IBranchPuller',
    ]


from zope.interface import (
    Attribute,
    Interface,
    )


class IBranchPuller(Interface):
    """The interface to the database for the branch puller."""

    MAXIMUM_MIRROR_FAILURES = Attribute(
        "The maximum number of failures before we disable mirroring.")

    MIRROR_TIME_INCREMENT = Attribute(
        "How frequently we mirror branches.")

    def acquireBranchToPull(*branch_types):
        """Return a Branch to pull and mark it as mirror-started.

        :param branch_types: Only return branches of these types.  Passing no
            types means consider all types (apart from REMOTE).
        :return: The branch object to pull next, or ``None`` if there is no
            branch to pull.
        """
