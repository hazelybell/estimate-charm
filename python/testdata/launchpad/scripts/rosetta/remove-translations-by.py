#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import _pythonpath

from lp.translations.scripts.remove_translations import RemoveTranslations


if __name__ == '__main__':
    script = RemoveTranslations(
        'lp.services.scripts.remove-translations',
        dbuser='rosettaadmin')
    script.run()
