# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.services.job.interfaces.job import IJobSource


class ITranslationPackagingJobSource(IJobSource):
    """Marker interface for Translation merge jobs."""
