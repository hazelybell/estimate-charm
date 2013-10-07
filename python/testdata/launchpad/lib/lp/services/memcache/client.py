# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Launchpad Memcache client."""

__metaclass__ = type
__all__ = []

import logging
import re

from lazr.restful.utils import get_current_browser_request
import memcache

from lp.services import features
from lp.services.config import config
from lp.services.timeline.requesttimeline import get_request_timeline


def memcache_client_factory():
    """Return a memcache.Client for Launchpad."""
    servers = [
        (host, int(weight)) for host, weight in re.findall(
            r'\((.+?),(\d+)\)', config.memcache.servers)]
    assert len(servers) > 0, "Invalid memcached server list %r" % (
        config.memcache.addresses,)
    return TimelineRecordingClient(servers)


class TimelineRecordingClient(memcache.Client):

    def __get_timeline_action(self, suffix, key):
        request = get_current_browser_request()
        timeline = get_request_timeline(request)
        return timeline.start("memcache-%s" % suffix, key)

    @property
    def _enabled(self):
        configured_value = features.getFeatureFlag('memcache')
        if configured_value is None:
            return True
        else:
            return configured_value

    def get(self, key):
        if not self._enabled:
            return None
        action = self.__get_timeline_action("get", key)
        try:
            return memcache.Client.get(self, key)
        finally:
            action.finish()

    def set(self, key, value, time=0, min_compress_len=0):
        if not self._enabled:
            return None
        action = self.__get_timeline_action("set", key)
        try:
            success = memcache.Client.set(self, key, value, time=time,
                min_compress_len=min_compress_len)
            if success:
                logging.debug("Memcache set succeeded for %s", key)
            else:
                logging.warn("Memcache set failed for %s", key)
            return success
        finally:
            action.finish()
