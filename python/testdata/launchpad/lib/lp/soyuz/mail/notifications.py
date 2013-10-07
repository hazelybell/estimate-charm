# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Event handlers that send email notifications."""

__metaclass__ = type

from zope.component import getUtility

from lp.services.config import config
from lp.services.database.sqlbase import block_implicit_flushes
from lp.services.mail.helpers import get_email_template
from lp.services.mail.mailwrapper import MailWrapper
from lp.services.mail.sendmail import (
    format_address,
    simple_sendmail,
    )
from lp.services.webapp.interfaces import ILaunchpadRoot
from lp.services.webapp.publisher import canonical_url


CC = "CC"


@block_implicit_flushes
def notify_new_ppa_subscription(subscription, event):
    """Notification that a new PPA subscription can be activated."""
    non_active_subscribers = subscription.getNonActiveSubscribers()

    archive = subscription.archive

    # We don't send notification emails for some PPAs, particularly those that
    # are purchased via the Software Centre, so that its users do not have to
    # learn about Launchpad.
    if archive.suppress_subscription_notifications:
        return

    registrant_name = subscription.registrant.displayname
    ppa_displayname = archive.displayname
    ppa_reference = "ppa:%s/%s" % (
        archive.owner.name, archive.name)
    ppa_description = archive.description
    subject = 'PPA access granted for ' + ppa_displayname

    template = get_email_template('ppa-subscription-new.txt', app='soyuz')

    for person, preferred_email in non_active_subscribers:
        to_address = [preferred_email.email]
        root = getUtility(ILaunchpadRoot)
        recipient_subscriptions_url = "%s~/+archivesubscriptions" % (
            canonical_url(root))
        description_blurb = '.'
        if ppa_description is not None and ppa_description != '':
            description_blurb = (
                ' and has the following description:\n\n%s' % ppa_description)
        replacements = {
            'recipient_name': person.displayname,
            'registrant_name': registrant_name,
            'registrant_profile_url': canonical_url(subscription.registrant),
            'ppa_displayname': ppa_displayname,
            'ppa_reference': ppa_reference,
            'ppa_description_blurb': description_blurb,
            'recipient_subscriptions_url': recipient_subscriptions_url,
            }
        body = MailWrapper(72).format(template % replacements,
                                      force_wrap=True)

        from_address = format_address(
            registrant_name, config.canonical.noreply_from_address)

        headers = {
            'Sender': config.canonical.bounce_address,
            }

        # If the registrant has a preferred email, then use it for the
        # Reply-To.
        if subscription.registrant.preferredemail:
            headers['Reply-To'] = format_address(
                registrant_name,
                subscription.registrant.preferredemail.email)

        simple_sendmail(from_address, to_address, subject, body, headers)
