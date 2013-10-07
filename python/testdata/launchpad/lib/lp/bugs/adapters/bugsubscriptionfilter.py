# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Adapt IStructuralSubscription to other types."""

__metaclass__ = type
__all__ = [
    'bugsubscriptionfilter_to_distribution',
    'bugsubscriptionfilter_to_product',
    ]


def bugsubscriptionfilter_to_distribution(bug_subscription_filter):
    """Adapt the `IBugSubscriptionFilter` to an `IDistribution`."""
    subscription = bug_subscription_filter.structural_subscription
    if subscription.distroseries is not None:
        return subscription.distroseries.distribution
    return subscription.distribution


def bugsubscriptionfilter_to_product(bug_subscription_filter):
    """Adapt the `IBugSubscriptionFilter` to an `IProduct`."""
    subscription = bug_subscription_filter.structural_subscription
    if subscription.productseries is not None:
        return subscription.productseries.product
    return subscription.product
