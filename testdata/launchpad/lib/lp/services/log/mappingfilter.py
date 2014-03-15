# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A logging.Filter to alter log levels of log records."""

__metaclass__ = type
__all__ = ['MappingFilter']


import logging


class MappingFilter(logging.Filter):
    """logging.Filter that alters the level of records using a mapping."""

    def __init__(self, mapping, name=''):
        """mapping is in the form {10: (8, 'DEBUG3')}"""
        logging.Filter.__init__(self, name)
        self.mapping = mapping
        self._dotted_name = name + '.'

    def filter(self, record):
        if (record.levelno in self.mapping and (
            not record.name or self.name == record.name
            or record.name.startswith(self._dotted_name))):
            record.levelno, record.levelname = self.mapping[record.levelno]
        return True
