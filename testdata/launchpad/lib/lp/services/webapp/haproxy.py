# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementation of the HAProxy probe URL."""


__metaclass__ = type
__all__ = [
    'HAProxyStatusView',
    'set_going_down_flag',
    'switch_going_down_flag',
    ]

from lp.services.config import config

# This is the global flag, when this is True, the HAProxy view
# will return 500, it returns 200 otherwise.
going_down_flag = False


def set_going_down_flag(state):
    """Sets the going_down_flag to state"""
    global going_down_flag
    going_down_flag = state


def switch_going_down_flag():
    """Switch the going down flag.

    This is is registered as a signal handler for HUP.
    """
    global going_down_flag
    going_down_flag = not going_down_flag


class HAProxyStatusView:
    """
    View implementing the HAProxy probe URL.

    HAProxy doesn't support programmatically taking servers in and our of
    rotation. It does however uses a probe URL that it scans regularly to see
    if the server is still alive. The /+haproxy is that URL for us.

    If it times out or returns a non-200 status, it will take the server out
    of rotation, until the probe works again.

    This allow us to send a signal (HUP) to the app servers when we want to
    restart them. The probe URL will then return 500 and the app server will
    be taken out of rotation. Once HAProxy reports that all connections to the
    app servers are finished, we can restart the server safely.

    The returned result code when the server is going down can be configured
    through the haproxy_status_view.going_down_status configuration variable.
    It defaults to 500 (as set in lib/lp/services/config/schema-lazr.conf).
    """

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def __call__(self):
        """Return 200 or going down status depending on the global flag."""
        global going_down_flag

        if going_down_flag:
            self.request.response.setStatus(
                config.haproxy_status_view.going_down_status)
            return u"May day! May day! I'm going down. Stop the flood gate."
        else:
            self.request.response.setStatus(200)
            return u"Everything is groovy. Keep them coming!"
