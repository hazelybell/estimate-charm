# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Functions and classes that are subscribed to registry events."""

__metaclass__ = type

__all__ = [
    'product_licenses_modified',
    ]

from datetime import datetime
import textwrap

from lazr.restful.utils import get_current_browser_request
import pytz
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.product import License
from lp.services.config import config
from lp.services.mail.helpers import get_email_template
from lp.services.mail.sendmail import (
    format_address,
    format_address_for_person,
    simple_sendmail,
    )
from lp.services.webapp.escaping import structured
from lp.services.webapp.publisher import canonical_url


def product_licenses_modified(product, event):
    """Send a notification if licences changed and a licence is special."""
    if LicenseNotification.needs_notification(product):
        notification = LicenseNotification(product)
        notification.send()
        notification.display()


class LicenseNotification:
    """Send notification about special licences to the user."""

    def __init__(self, product):
        self.product = product

    @staticmethod
    def needs_notification(product):
        licenses = list(product.licenses)
        return (
            License.OTHER_PROPRIETARY in licenses
            or License.OTHER_OPEN_SOURCE in licenses
            or [License.DONT_KNOW] == licenses)

    def getTemplateName(self):
        """Return the name of the email template for the licensing case."""
        licenses = list(self.product.licenses)
        if [License.DONT_KNOW] == licenses:
            template_name = 'product-license-dont-know.txt'
        elif License.OTHER_PROPRIETARY in licenses:
            template_name = 'product-license-other-proprietary.txt'
        else:
            template_name = 'product-license-other-open-source.txt'
        return template_name

    def getCommercialUseMessage(self):
        """Return a message explaining the current commercial subscription."""
        commercial_subscription = self.product.commercial_subscription
        if commercial_subscription is None:
            return ''
        iso_date = commercial_subscription.date_expires.date().isoformat()
        if not self.product.has_current_commercial_subscription:
            message = "%s's commercial subscription expired on %s."
        elif 'complimentary' in commercial_subscription.sales_system_id:
            message = (
                "%s's complimentary commercial subscription expires on %s.")
        else:
            message = "%s's commercial subscription expires on %s."
        message = message % (self.product.displayname, iso_date)
        return textwrap.fill(message, 72)

    def send(self):
        """Send a message to the user about the product's licence."""
        if not self.needs_notification(self.product):
            # The project has a common licence.
            return False
        maintainer = self.product.owner
        if maintainer.is_team:
            user_address = maintainer.getTeamAdminsEmailAddresses()
        else:
            user_address = format_address_for_person(maintainer)
        from_address = format_address(
            "Launchpad", config.canonical.noreply_from_address)
        commercial_address = format_address(
            'Commercial', 'commercial@launchpad.net')
        substitutions = dict(
            user_displayname=maintainer.displayname,
            user_name=maintainer.name,
            product_name=self.product.name,
            product_url=canonical_url(self.product),
            commercial_use_expiration=self.getCommercialUseMessage(),
            )
        # Email the user about licence policy.
        subject = (
            "Licence information for %(product_name)s "
            "in Launchpad" % substitutions)
        template = get_email_template(
            self.getTemplateName(), app='registry')
        message = template % substitutions
        simple_sendmail(
            from_address, user_address,
            subject, message, headers={'Reply-To': commercial_address})
        # Inform that Launchpad recognized the licence change.
        self._addLicenseChangeToReviewWhiteboard()
        return True

    def display(self):
        """Show a message in a browser page about the product's licence."""
        request = get_current_browser_request()
        message = self.getCommercialUseMessage()
        if request is None or message == '':
            return False
        safe_message = structured(
            '%s<br />Learn more about '
            '<a href="https://help.launchpad.net/CommercialHosting">'
            'commercial subscriptions</a>', message)
        request.response.addNotification(safe_message)
        return True

    @staticmethod
    def _formatDate(now=None):
        """Return the date formatted for messages."""
        if now is None:
            now = datetime.now(tz=pytz.UTC)
        return now.strftime('%Y-%m-%d')

    def _addLicenseChangeToReviewWhiteboard(self):
        """Update the whiteboard for the reviewer's benefit."""
        now = self._formatDate()
        whiteboard = 'User notified of licence policy on %s.' % now
        naked_product = removeSecurityProxy(self.product)
        if naked_product.reviewer_whiteboard is None:
            naked_product.reviewer_whiteboard = whiteboard
        else:
            naked_product.reviewer_whiteboard += '\n' + whiteboard
