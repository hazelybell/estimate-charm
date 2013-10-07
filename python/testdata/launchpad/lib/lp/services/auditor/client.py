# Copyright 2012-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Client that will send and receive audit logs to an auditor instance."""

__metaclass__ = type
__all__ = [
    'AuditorClient',
    ]

from auditorclient.client import Client
from lazr.restful.utils import get_current_browser_request

from lp.services.config import config
from lp.services.enterpriseid import (
    enterpriseids_to_objects,
    object_to_enterpriseid,
    )
from lp.services.timeline.requesttimeline import get_request_timeline


class AuditorClient(Client):

    def __init__(self):
        super(AuditorClient, self).__init__(
            config.auditor.host, config.auditor.port)

    def __get_timeline_action(self, suffix, obj, operation, actorobj):
        data = "Object: %s; Operation: %s, Actor: %s" % (
            obj, operation, actorobj)
        timeline = get_request_timeline(get_current_browser_request())
        return timeline.start("auditor-%s" % suffix, data)

    def send(self, obj, operation, actorobj, comment=None, details=None):
        obj = object_to_enterpriseid(obj)
        actorobj = object_to_enterpriseid(actorobj)
        action = self.__get_timeline_action("send", obj, operation, actorobj)
        try:
            return super(AuditorClient, self).send(
                obj, operation, actorobj, comment, details)
        finally:
            action.finish()

    def _convert_to_enterpriseid(self, obj):
        if isinstance(obj, (list, tuple)):
            return [object_to_enterpriseid(o) for o in obj]
        else:
            return object_to_enterpriseid(obj)

    def receive(self, obj=None, operation=None, actorobj=None, limit=None):
        if obj:
            obj = self._convert_to_enterpriseid(obj)
        if actorobj:
            actorobj = self._convert_to_enterpriseid(actorobj)
        action = self.__get_timeline_action(
            "receive", obj, operation, actorobj)
        try:
            logs = super(AuditorClient, self).receive(
                obj, operation, actorobj, limit)
        finally:
            action.finish()
        # Process the actors and objects back from enterprise ids.
        eids = set()
        for entry in logs['log-entries']:
            eids |= set([entry['actor'], entry['object']])
        map_eids_to_obj = enterpriseids_to_objects(eids)
        for entry in logs['log-entries']:
            entry['actor'] = map_eids_to_obj.get(entry['actor'], None)
            entry['object'] = map_eids_to_obj.get(entry['object'], None)
        return logs['log-entries']
