# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Contains the seting auditor used to clean up security.cfg."""

__metaclass__ = type

__all__ = [
    "SettingsAuditor",
    ]

from collections import defaultdict
import re


class SettingsAuditor:
    """Reads the security.cfg file and collects errors.

    We can't just use ConfigParser for this case, as we're doing our own
    specialized parsing--not interpreting the settings, but verifying."""

    header_regex = re.compile(r'.*?(?=\[)', re.MULTILINE|re.DOTALL)
    section_regex = re.compile(
        r'\[.*?\].*?(?=(\[)|($\Z))', re.MULTILINE|re.DOTALL)
    section_label_regex = re.compile(r'\[.*\]')

    def __init__(self, data):
        self.data = data
        self.errors = {}
        self.current_section = ''
        self.observed_settings = defaultdict(lambda: 0)

    def _getHeader(self):
        """Removes the header comments from the security file.

        The comments at the start of the file aren't something we
        want to kill.
        """
        header = self.header_regex.match(self.data)
        if header is not None:
            header = header.group()
            self.data = self.data.replace(header, '')
        return header

    def _strip(self, data):
        data = data.split('\n')
        data = [d.strip() for d in data]
        return '\n'.join(d for d in data if not (d.startswith('#') or d == ''))

    def _getSectionName(self, line):
        if line.strip().startswith('['):
            return self.section_regex.match(line).group()
        else:
            return None

    def _separateConfigBlocks(self):
        # We keep the copy of config_labels so we can keep them in order.
        self.config_blocks = {}
        self.config_labels = []
        self.data = self._strip(self.data)
        while self.data != '':
            section = self.section_regex.match(self.data)
            section = section.group()
            self.data = self.data.replace(section, '')
            label = self.section_label_regex.match(section).group()
            self.config_labels.append(label)
            self.config_blocks[label] = section

    def _processBlocks(self):
        for block in self.config_labels:
            data = set(self.config_blocks[block].split('\n')[1:])
            data.discard('')
            data = [line for line in sorted(data)
                    if line.strip() != '' and
                    not line.strip().startswith('#')]
            self._checkForDupes(data, block)
            data = '\n'.join([block] + data)
            self.config_blocks[block] = data

    def _checkForDupes(self, data, label):
        settings = defaultdict(lambda: 0)
        for line in data:
            settings[self._getSetting(line)] += 1
        dupe_settings = [setting for setting in settings.keys()
                    if settings[setting] > 1]
        if dupe_settings != []:
            self.errors[label] = dupe_settings

    def _getSetting(self, line):
        return line.split()[0]

    def audit(self):
        header = self._getHeader()
        self._separateConfigBlocks()
        self._processBlocks()
        data = []
        for label in self.config_labels:
            data.append(self.config_blocks[label])
        return '%s%s' % (header, '\n\n'.join(data))

    @property
    def error_data(self):
        error_data = []
        error_data.append("The following errors were found in security.cfg")
        error_data.append("-----------------------------------------------")
        for section in self.errors.keys():
            error_data.append("In section: %s" % section)
            for setting in self.errors[section]:
                error_data.append('\tDuplicate setting found: %s' % setting)
        return '\n'.join(error_data)
