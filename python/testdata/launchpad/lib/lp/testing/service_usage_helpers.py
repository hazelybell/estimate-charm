# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper functions dealing with IServiceUsage."""
__metaclass__ = type

from zope.component import getUtility

from lp.app.enums import ServiceUsage
from lp.code.enums import BranchType
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.registry.interfaces.product import IProduct
from lp.testing import celebrity_logged_in
from lp.testing.factory import LaunchpadObjectFactory


def set_service_usage(pillar_name, **kw):
    factory = LaunchpadObjectFactory()
    with celebrity_logged_in('admin'):
        pillar = getUtility(IPillarNameSet)[pillar_name]
        for attr, service_usage_name in kw.items():
            service_usage = getattr(ServiceUsage, service_usage_name)
            if attr == 'bug_tracking_usage':
                pillar.official_malone = (
                    service_usage == ServiceUsage.LAUNCHPAD)
                if service_usage == ServiceUsage.EXTERNAL:
                    pillar.bugtracker = factory.makeBugTracker()

            # if we're setting codehosting on product things get trickier.
            elif attr == 'codehosting_usage' and IProduct.providedBy(pillar):
                if service_usage == ServiceUsage.LAUNCHPAD:
                    branch = factory.makeProductBranch(product=pillar)
                    product_series = factory.makeProductSeries(
                        product=pillar,
                        branch=branch)
                    pillar.development_focus = product_series
                elif service_usage == ServiceUsage.EXTERNAL:
                    branch = factory.makeProductBranch(
                        product=pillar,
                        branch_type=BranchType.MIRRORED)
                    product_series = factory.makeProductSeries(
                        product=pillar,
                        branch=branch)
                    pillar.development_focus = product_series
                elif service_usage == ServiceUsage.UNKNOWN:
                    branch = factory.makeProductBranch(product=pillar)
                    product_series = factory.makeProductSeries(
                        product=pillar)
                    pillar.development_focus = product_series
            else:
                setattr(pillar, attr, service_usage)
