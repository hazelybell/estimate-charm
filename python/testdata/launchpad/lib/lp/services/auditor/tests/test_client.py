# Copyright 2012-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lazr.restful.utils import get_current_browser_request

from lp.services.auditor.client import AuditorClient
from lp.services.enterpriseid import object_to_enterpriseid
from lp.services.timeline.requesttimeline import get_request_timeline
from lp.testing import TestCaseWithFactory
from lp.testing.layers import AuditorLayer


class TestAuditorClient(TestCaseWithFactory):

    layer = AuditorLayer

    def assertAction(self, category, data):
        timeline = get_request_timeline(get_current_browser_request())
        action = timeline.actions[-1]
        self.assertEqual(category, action.category)
        self.assertEqual(data, action.detail)

    def test_send_and_receive(self):
        # We can use .send() and .receive() on AuditorClient to log.
        actor = self.factory.makePerson()
        pu = self.factory.makePackageUpload()
        client = AuditorClient()
        result = client.send(pu, 'packageupload-accepted', actor)
        self.assertEqual('Operation recorded.', result)
        data = "Object: %s; Operation: packageupload-accepted, Actor: %s" % (
                object_to_enterpriseid(pu), object_to_enterpriseid(actor))
        self.assertAction('auditor-send', data)
        result = client.receive(obj=pu)
        del result[0]['date'] # Ignore the date.
        expected = [{
            u'comment': u'', u'details': u'', u'actor': actor,
            u'operation': u'packageupload-accepted', u'object': pu}]
        self.assertContentEqual(expected, result)
        self.assertAction(
            'auditor-receive', "Object: %s; Operation: None, Actor: None" % (
                object_to_enterpriseid(pu)))

    def test_multiple_receive(self):
        # We can ask AuditorClient for a number of operations.
        actor = self.factory.makePerson()
        actor2 = self.factory.makePerson()
        client = AuditorClient()
        client.send(actor, 'person-deleted', actor)
        client.send(actor2, 'person-undeleted', actor)
        result = client.receive(
            obj=(actor, actor2),
            operation=('person-deleted', 'person-undeleted'))
        self.assertEqual(2, len(result))
        for r in result:
            del r['date'] # Ignore the date.
        expected = [
            {u'comment': u'', u'details': u'', u'actor': actor,
            u'operation': u'person-deleted', u'object': actor},
            {u'comment': u'', u'details': u'', u'actor': actor,
            u'operation': u'person-undeleted', u'object': actor2}]
        self.assertContentEqual(expected, result)
