# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database class for table PublisherConfig."""

__metaclass__ = type

__all__ = [
    'PublisherConfig',
    'PublisherConfigSet',
    ]

from storm.locals import (
    Int,
    Reference,
    Storm,
    Unicode,
    )
from zope.interface import implements

from lp.archivepublisher.interfaces.publisherconfig import (
    IPublisherConfig,
    IPublisherConfigSet,
    )
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )


class PublisherConfig(Storm):
    """See `IArchiveAuthToken`."""
    implements(IPublisherConfig)
    __storm_table__ = 'PublisherConfig'

    id = Int(primary=True)

    distribution_id = Int(name='distribution', allow_none=False)
    distribution = Reference(distribution_id, 'Distribution.id')

    root_dir = Unicode(name='root_dir', allow_none=False)

    base_url = Unicode(name='base_url', allow_none=False)

    copy_base_url = Unicode(name='copy_base_url', allow_none=False)


class PublisherConfigSet:
    """See `IPublisherConfigSet`."""
    implements(IPublisherConfigSet)
    title = "Soyuz Publisher Configurations"

    def new(self, distribution, root_dir, base_url, copy_base_url):
        """Make and return a new `PublisherConfig`."""
        store = IMasterStore(PublisherConfig)
        pubconf = PublisherConfig()
        pubconf.distribution = distribution
        pubconf.root_dir = root_dir
        pubconf.base_url = base_url
        pubconf.copy_base_url = copy_base_url
        store.add(pubconf)
        return pubconf

    def getByDistribution(self, distribution):
        """See `IArchiveAuthTokenSet`."""
        return IStore(PublisherConfig).find(
            PublisherConfig,
            PublisherConfig.distribution_id == distribution.id).one()
