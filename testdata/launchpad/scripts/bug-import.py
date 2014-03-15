#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import _pythonpath

import logging

import transaction
from zope.component import getUtility

from lp.bugs.scripts.bugimport import BugImporter
from lp.registry.interfaces.product import IProductSet
from lp.services.config import config
from lp.services.scripts.base import LaunchpadScript
from lp.testing.factory import LaunchpadObjectFactory


class BugImportScript(LaunchpadScript):

    description = "Import bugs into Launchpad from XML."
    loglevel = logging.INFO

    def add_my_options(self):
        self.parser.add_option(
            '-p', '--product', metavar='PRODUCT', action='store',
            help='Which product to export', type='string', dest='product',
            default=None)
        self.parser.add_option(
            '--cache', metavar='FILE', action='store',
            help='Cache for bug ID mapping', type='string',
            dest='cache_filename', default='bug-map.pickle')
        # XXX: jamesh 2007-04-11 bugs=86352
        # Not verifying users created by a bug import can result in
        # problems with mail notification, so should not be used for
        # imports.
        self.parser.add_option(
            '--dont-verify-users', dest='verify_users',
            help="Don't verify newly created users", action='store_false',
            default=True)
        self.parser.add_option(
            '--testing', dest="testing", action="store_true", help=(
                "Testing mode; if --product=name is omitted, create a "
                "product with Launchpad's test object factory. Do *not* "
                "use in production!"),
            default=False)

    def create_test_product(self):
        """Create a test product with `LaunchpadObjectFactory`.

        Returns the new object's name.
        """
        factory = LaunchpadObjectFactory()
        product = factory.makeProduct(official_malone=True)
        transaction.commit()
        return product.name

    def main(self):
        if self.options.product is None:
            if self.options.testing:
                self.options.product = self.create_test_product()
                self.logger.info("Product %s created", self.options.product)
            else:
                self.parser.error('No product specified')
        if len(self.args) != 1:
            self.parser.error('Please specify a bug XML file to import')
        bugs_filename = self.args[0]

        # don't send email
        send_email_data = """
            [immediate_mail]
            send_email: False
            """
        config.push('send_email_data', send_email_data)
        self.login('bug-importer@launchpad.net')

        product = getUtility(IProductSet).getByName(self.options.product)
        if product is None:
            self.parser.error('Product %s does not exist'
                              % self.options.product)

        importer = BugImporter(
            product, bugs_filename, self.options.cache_filename,
            verify_users=self.options.verify_users, logger=self.logger)
        importer.importBugs(self.txn)
        config.pop('send_email_data')


if __name__ == '__main__':
    script = BugImportScript('lp.services.scripts.bugimport')
    script.run()
