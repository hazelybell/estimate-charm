#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Re-upload translations from given packages."""

__metaclass__ = type

import _pythonpath

from lp.translations.scripts.reupload_translations import (
    ReuploadPackageTranslations,
    )


if __name__ == '__main__':
    script = ReuploadPackageTranslations('reupload-translations')
    script.run()
