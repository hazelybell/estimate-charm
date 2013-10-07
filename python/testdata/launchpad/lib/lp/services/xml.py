# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Validate XML documents against a schema."""

__all__ = [
    'XMLValidator',
    'RelaxNGValidator',
    ]


import os
from tempfile import NamedTemporaryFile

from lp.services.helpers import simple_popen2


class XMLValidator:
    """A validator for XML files against a schema."""

    SCHEMA_ARGUMENT = 'schema'

    def __init__(self, schema_filename):
        """Create a validator instance.

        :param schema_filename: The name of a file containing the schema.
        """
        self.schema_filename = schema_filename
        self._errors = ''


    def validate(self, xml):
        """Validate the string xml

        :return: True, if xml is valid, else False.
        """
        # XXX Abel Deuring, 2008-03-20
        # The original implementation of the validation used the lxml
        # package. Unfortunately, running lxml's Relax NG validator
        # caused segfaults during PQM test runs, hence this class uses
        # an external validator.

        # Performance penalty of the external validator:
        # Using the lxml validator, the tests in this module need ca.
        # 3 seconds on a 2GHz Core2Duo laptop.
        # If the xml data to be validated is passed to xmllint via
        # lp.services.helpers.simple_popen2, the run time
        # of the tests is 38..40 seconds; if the validation input
        # is not passed via stdin but saved in a temporary file,
        # the tests need 28..30 seconds.

        xml_file = NamedTemporaryFile()
        xml_file.write(xml)
        xml_file.flush()
        command = ['xmllint', '--noout', '--nonet',
                   '--%s' % self.SCHEMA_ARGUMENT,
                   self.schema_filename, xml_file.name]
        local_catalog_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "tests", "testfiles",
                         "catalog", "catalog"))
        catalogs = " ".join(
            [local_catalog_path, "/etc/xml/catalog"])
        env = {"XML_CATALOG_FILES": catalogs}
        result = simple_popen2(command, '', env=env).strip()

        # The output consists of lines describing possible errors; the
        # last line is either "(file) fails to validate" or
        # "(file) validates".
        parts = result.rsplit('\n', 1)
        if len(parts) > 1:
            self._errors = parts[0]
            status = parts[1]
        else:
            self._errors = ''
            status = parts[0]
        if status == xml_file.name + ' fails to validate':
            return False
        elif status == xml_file.name + ' validates':
            return True
        else:
            raise AssertionError(
                'Unexpected result of running xmllint: %s' % result)

    @property
    def error_log(self):
        """A string with the errors detected by the validator.

        Each line contains one error; if the validation was successful,
        error_log is the empty string.
        """
        return self._errors


class RelaxNGValidator(XMLValidator):
    """A validator for Relax NG schemas."""

    SCHEMA_ARGUMENT = 'relaxng'
