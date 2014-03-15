# Copyright 2010 Canonical Ltd. This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'IPOFileStatsJobSource',
    ]

from lp.services.job.interfaces.job import IJobSource


class IPOFileStatsJobSource(IJobSource):
    """A source for jobs to update POFile statistics."""
