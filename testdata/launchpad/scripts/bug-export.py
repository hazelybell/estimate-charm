#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
import _pythonpath

import sys

import transaction
from zope.component import getUtility

from lp.bugs.scripts.bugexport import export_bugtasks
from lp.registry.interfaces.product import IProductSet
from lp.services.scripts.base import LaunchpadScript


class BugExportScript(LaunchpadScript):

    description = "Export bugs for a Launchpad product as XML"

    def add_my_options(self):
        self.parser.add_option(
            '-o', '--output', metavar='FILE', action='store',
            help='Export bugs to this file', type='string', dest='output')
        self.parser.add_option(
            '-p', '--product', metavar='PRODUCT', action='store',
            help='Which product to export', type='string', dest='product')
        self.parser.add_option(
            '--include-private', action='store_true',
            help='Include private bugs in dump', dest='include_private',
            default=False)

    def main(self):
        if self.options.product is None:
            self.parser.error('No product specified')
        output = sys.stdout
        if self.options.output is not None:
            output = open(self.options.output, 'wb')

        product = getUtility(IProductSet).getByName(self.options.product)
        if product is None:
            self.parser.error(
                'Product %s does not exist' % self.options.product)

        export_bugtasks(
            transaction, product, output,
            include_private=self.options.include_private)

if __name__ == '__main__':
    BugExportScript("bug-export").run()
