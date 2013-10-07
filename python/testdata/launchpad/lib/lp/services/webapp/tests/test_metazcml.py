# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.configuration import xmlconfig

from lp.testing import TestCase
from lp.testing.fakemethod import FakeMethod


class TestCallDirective(TestCase):

    def test_call(self):
        directive = """ 
            <call callable="%(this)s.callable" />
            """ % dict(this=this)
        xmlconfig.string(zcml_configure % directive)
        self.assertEqual(1, callable.call_count)


callable = FakeMethod()
this = "lp.services.webapp.tests.test_metazcml"
zcml_configure = """
    <configure xmlns="http://namespaces.zope.org/zope">
      <include package="lp.services.webapp" file="meta.zcml" />
      %s
    </configure>
    """
