# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.services.database.constants import UTC_NOW


def cve_modified(cve, object_modified_event):
    cve.datemodified = UTC_NOW

