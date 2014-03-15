# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Support for the lp.registry.javascript.milestoneoverlay YUIXHR tests.
"""

__metaclass__ = type
__all__ = []

from lp.services.webapp.publisher import canonical_url
from lp.testing import person_logged_in
from lp.testing.factory import LaunchpadObjectFactory
from lp.testing.yuixhr import (
    login_as_person,
    make_suite,
    setup,
    )


factory = LaunchpadObjectFactory()


@setup
def setup(request, data):
    owner = factory.makePerson()
    with person_logged_in(owner):
        product = factory.makeProduct(name="my-test-project", owner=owner)
        product_series = factory.makeProductSeries(
            name="new-series", product=product)
        data['product'] = product
        data['series_uri'] = canonical_url(
            product_series, path_only_if_possible=True)
        data['milestone_form_uri'] = (
            canonical_url(product_series) + '/+addmilestone/++form++')
    login_as_person(owner)


def test_suite():
    return make_suite(__name__)
