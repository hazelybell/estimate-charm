# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import re


def valid_cve(name):
    pat = r"^(19|20)\d\d-\d{4}$"
    if re.match(pat, name):
        return True
    return False

