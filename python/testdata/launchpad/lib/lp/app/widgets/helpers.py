# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers for Launchpad widgets."""

import os


def get_widget_template(filename):
    """Return the content of lib/lp/app/widgets/templates/<filename>."""
    here = os.path.dirname(__file__)
    template_path = os.path.join(here, 'templates', filename)
    file = open(template_path)
    try:
        return file.read()
    finally:
        file.close()
