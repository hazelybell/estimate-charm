# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views for QuestionSubscription."""

__metaclass__ = type
__all__ = [
    'QuestionPortletSubscribersWithDetails',
    ]

from lazr.delegates import delegates
from lazr.restful.interfaces import IWebServiceClientRequest
from simplejson import dumps
from zope.traversing.browser import absoluteURL

from lp.answers.interfaces.question import IQuestion
from lp.answers.interfaces.questionsubscription import IQuestionSubscription
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    )


class QuestionPortletSubscribersWithDetails(LaunchpadView):
    """View that returns a JSON dump of subscriber details for a question."""

    @cachedproperty
    def api_request(self):
        return IWebServiceClientRequest(self.request)

    def direct_subscriber_data(self, question):
        """Get the direct subscriber data.

        This method is isolated from the subscriber_data_js so that query
        count testing can be done accurately and robustly.
        """
        data = []
        details = list(question.getDirectSubscribersWithDetails())
        for person, subscription in details:
            can_edit = subscription.canBeUnsubscribedByUser(self.user)
            if person.private and not can_edit:
                # Skip private teams user is not a member of.
                continue

            subscriber = {
                'name': person.name,
                'display_name': person.displayname,
                'web_link': canonical_url(person, rootsite='mainsite'),
                'self_link': absoluteURL(person, self.api_request),
                'is_team': person.is_team,
                'can_edit': can_edit
                }
            record = {
                'subscriber': subscriber,
                'subscription_level': 'Direct',
                }
            data.append(record)
        return data

    @property
    def subscriber_data_js(self):
        """Return subscriber_ids in a form suitable for JavaScript use."""
        question = IQuestion(self.context)
        data = self.direct_subscriber_data(question)

        others = question.getIndirectSubscribers()
        for person in others:
            if person == self.user:
                # Skip the current user viewing the page.
                continue
            subscriber = {
                'name': person.name,
                'display_name': person.displayname,
                'web_link': canonical_url(person, rootsite='mainsite'),
                'self_link': absoluteURL(person, self.api_request),
                'is_team': person.is_team,
                'can_edit': False,
                }
            record = {
                'subscriber': subscriber,
                'subscription_level': 'Indirect',
                }
            data.append(record)
        return dumps(data)

    def render(self):
        """Override the default render() to return only JSON."""
        self.request.response.setHeader('content-type', 'application/json')
        return self.subscriber_data_js


class SubscriptionAttrDecorator:
    """A QuestionSubscription with added attributes for HTML/JS."""
    delegates(IQuestionSubscription, 'subscription')

    def __init__(self, subscription):
        self.subscription = subscription

    @property
    def css_name(self):
        return 'subscriber-%s' % self.subscription.person.id
