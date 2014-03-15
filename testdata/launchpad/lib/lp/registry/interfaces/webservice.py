# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""All the interfaces that are exposed through the webservice."""

__all__ = [
    'DerivationError',
    'ICommercialSubscription',
    'IDistribution',
    'IDistributionMirror',
    'IDistributionSet',
    'IDistributionSourcePackage',
    'IDistroSeries',
    'IDistroSeriesDifference',
    'IDistroSeriesDifferenceComment',
    'IGPGKey',
    'IHasMilestones',
    'IIrcID',
    'IJabberID',
    'IMilestone',
    'IPerson',
    'IPersonSet',
    'IPillar',
    'IPillarNameSet',
    'IProduct',
    'IProductRelease',
    'IProductReleaseFile',
    'IProductSeries',
    'IProductSet',
    'IProjectGroup',
    'IProjectGroupMilestone',
    'IProjectGroupSet',
    'IServiceFactory',
    'ISharingService',
    'ISSHKey',
    'ISourcePackage',
    'ISourcePackageName',
    'ITeam',
    'ITeamMembership',
    'ITimelineProductSeries',
    'IWikiName',
    ]

# XXX: JonathanLange 2010-11-09 bug=673083: Legacy work-around for circular
# import bugs.  Break this up into a per-package thing.
from lp import _schema_circular_imports
from lp.app.interfaces.services import IServiceFactory
from lp.registry.interfaces.commercialsubscription import (
    ICommercialSubscription,
    )
from lp.registry.interfaces.distribution import (
    IDistribution,
    IDistributionSet,
    )
from lp.registry.interfaces.distributionmirror import IDistributionMirror
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.distroseries import (
    DerivationError,
    IDistroSeries,
    )
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifference,
    )
from lp.registry.interfaces.distroseriesdifferencecomment import (
    IDistroSeriesDifferenceComment,
    )
from lp.registry.interfaces.gpg import IGPGKey
from lp.registry.interfaces.irc import IIrcID
from lp.registry.interfaces.jabber import IJabberID
from lp.registry.interfaces.milestone import (
    IHasMilestones,
    IMilestone,
    IProjectGroupMilestone,
    )
from lp.registry.interfaces.person import (
    IPerson,
    IPersonSet,
    ITeam,
    )
from lp.registry.interfaces.pillar import (
    IPillar,
    IPillarNameSet,
    )
from lp.registry.interfaces.product import (
    IProduct,
    IProductSet,
    )
from lp.registry.interfaces.productrelease import (
    IProductRelease,
    IProductReleaseFile,
    )
from lp.registry.interfaces.productseries import (
    IProductSeries,
    ITimelineProductSeries,
    )
from lp.registry.interfaces.projectgroup import (
    IProjectGroup,
    IProjectGroupSet,
    )
from lp.registry.interfaces.sharingservice import ISharingService
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.registry.interfaces.sourcepackagename import ISourcePackageName
from lp.registry.interfaces.ssh import ISSHKey
from lp.registry.interfaces.teammembership import ITeamMembership
from lp.registry.interfaces.wikiname import IWikiName


_schema_circular_imports
