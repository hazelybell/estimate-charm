# -*- python -*-
# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

'''Launch a mock Swift service.'''

__metaclass__ = type
__all__ = []

import os.path
import logging

import twisted.web.server
from twisted.application import internet, service

logging.basicConfig()

from s4 import hollow

storedir = os.environ['HOLLOW_ROOT']
assert os.path.exists(storedir)

application = service.Application('hollow')
root = hollow.Root(storage_dir=storedir, hostname='localhost')

# make sure "the bucket" is created
root.swift.addBucket("the bucket")
site = twisted.web.server.Site(root)

port = int(os.environ['HOLLOW_PORT'])

sc = service.IServiceCollection(application)
internet.TCPServer(port, site).setServiceParent(sc)
