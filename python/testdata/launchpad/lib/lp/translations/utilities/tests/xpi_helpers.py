# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper methods for XPI testing"""
__metaclass__ = type

__all__ = [
    'access_key_source_comment',
    'command_key_source_comment',
    'get_en_US_xpi_file_to_import',
    ]

import os.path
import tempfile
from textwrap import dedent
import zipfile

import lp.translations


command_key_source_comment = dedent(u"""
    Select the shortcut key that you want to use. It should be translated,
    but often shortcut keys (for example Ctrl + KEY) are not changed from
    the original. If a translation already exists, please don't change it
    if you are not sure about it. Please find the context of the key from
    the end of the 'Located in' text below.
    """).strip()

access_key_source_comment = dedent(u"""
    Select the access key that you want to use. These have to be
    translated in a way that the selected character is present in the
    translated string of the label being referred to, for example 'i' in
    'Edit' menu item in English. If a translation already exists, please
    don't change it if you are not sure about it. Please find the context
    of the key from the end of the 'Located in' text below.
    """).strip()


def get_en_US_xpi_file_to_import(subdir):
    """Return an en-US.xpi file object ready to be imported.

    The file is generated from utilities/tests/firefox-data/<subdir>.
    """
    # en-US.xpi file is a ZIP file which contains embedded JAR file (which is
    # also a ZIP file) and a couple of other files.  Embedded JAR file is
    # named 'en-US.jar' and contains translatable resources.

    # Get the root path where the data to generate .xpi file is stored.
    test_root = os.path.join(
        os.path.dirname(lp.translations.__file__),
        'utilities/tests/firefox-data', subdir)

    # First create a en-US.jar file to be included in XPI file.
    jarfile = tempfile.TemporaryFile()
    jar = zipfile.ZipFile(jarfile, 'w')
    jarlist = []
    data_dir = os.path.join(test_root, 'en-US-jar/')
    for root, dirs, files in os.walk(data_dir):
        for name in files:
            relative_dir = root[len(data_dir):].strip('/')
            jarlist.append(os.path.join(relative_dir, name))
    for file_name in jarlist:
        f = open(os.path.join(data_dir, file_name), 'r')
        jar.writestr(file_name, f.read())
    jar.close()
    jarfile.seek(0)

    # Add remaining bits and en-US.jar to en-US.xpi.

    xpifile = tempfile.TemporaryFile()
    xpi = zipfile.ZipFile(xpifile, 'w')
    xpilist = os.listdir(test_root)
    xpilist.remove('en-US-jar')
    for file_name in xpilist:
        f = open(os.path.join(test_root, file_name), 'r')
        xpi.writestr(file_name, f.read())
    xpi.writestr('chrome/en-US.jar', jarfile.read())
    xpi.close()
    xpifile.seek(0)

    return xpifile
