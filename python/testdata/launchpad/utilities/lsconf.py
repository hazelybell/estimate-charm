#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Create lazr.config schema and confs from ZConfig data."""

__metatype__ = type

# Scripts may have relative imports.
import _pythonpath

from operator import attrgetter
from optparse import OptionParser
import os
import sys
from textwrap import dedent

from lazr.config import ImplicitTypeSchema

import lp.services.config


_schema_dir = os.path.abspath(os.path.dirname(lp.services.config.__file__))
_root = os.path.dirname(os.path.dirname(os.path.dirname(_schema_dir)))


class Configuration:
    """A lazr.config configuration."""
    _schema_path = os.path.join(_schema_dir, 'schema-lazr.conf')

    def __init__(self, config):
        self.config = config

    @classmethod
    def load(cls, conf_path, schema_path=None):
        """Initialize the Configuration.

        :conf_path: The path to the lazr.config conf file.
        :schema_path: The path to the lazr.config schema that defines
            the configuration.
        """
        if schema_path is None:
            schema_path = cls._schema_path
        schema = ImplicitTypeSchema(schema_path)
        return cls(schema.load(conf_path))

    def config_file_for_value(self, section, key):
        """Return the local path to the file that sets the section key."""
        conf_file_name = self.config.schema.filename
        value = section[key]
        previous_config_data = self.config.data
        # Walk the stack of config_data until a change is found.
        for config_data in self.config.overlays:
            if (section.name in config_data
                and config_data[section.name][key] != value):
                conf_file_name = previous_config_data.filename
                break
            previous_config_data = config_data
        conf_path = os.path.abspath(conf_file_name)
        return conf_path[len(_root) + 1:]

    def list_config(self, verbose=False, section_name=None):
        """Print all the sections and keys in a configuration.

        Print the final state of configuration after all the conf files
        are loaded.

        :param verbose: If True, each key has a comment stating where it
            was defined.
        :param section_name: Only print the named section.
        """
        print '# This configuration derives from:'
        for config_data in self.config.overlays:
            print '#     %s' % config_data.filename
        print
        name_key = attrgetter('name')
        for count, section in enumerate(sorted(self.config, key=name_key)):
            if section_name is not None and section_name != section.name:
                continue
            if count > 0:
                # Separate sections by a blank line, or two when verbose.
                print
            print '[%s]' % section.name
            if verbose and section.optional:
                print '# This section is optional.\n'
            for count, key in enumerate(sorted(section)):
                if verbose:
                    if count > 0:
                        # Separate keys by a blank line.
                        print
                    conf_file_name = self.config_file_for_value(section, key)
                    print '# Defined in: %s' % conf_file_name
                print '%s: %s' % (key, section[key])


def get_option_parser():
    """Return the option parser for this program."""
    usage = dedent("""    %prog [options] lazr-config.conf

    List all the sections and keys in an environment's lazr configuration.
    The configuration is assembled from the schema and conf files. Verbose
    annotates each key with the location of the file that set its value.
    The 'section' option limits the list to just the named section.""")
    parser = OptionParser(usage=usage)
    parser.add_option(
        "-l", "--schema", dest="schema_path",
        help="the path to the lazr.config schema file")
    parser.add_option(
        "-v", "--verbose", action="store_true",
        help="explain where the section and keys are set")
    parser.add_option(
        "-s", "--section", dest="section_name",
        help="restrict the listing to the section")
    parser.add_option(
        '-i', "--instance", dest="instance_name",
        help="the configuration instance to use")
    return parser


def main(argv=None):
    """Run the command line operations."""
    if argv is None:
        argv = sys.argv
    parser = get_option_parser()
    (options, arguments) = parser.parse_args(args=argv[1:])
    if len(arguments) == 0:
        canonical_config = lp.services.config.config
        if options.instance_name:
            canonical_config.setInstance(options.instance_name)
        canonical_config._getConfig()
        configuration = Configuration(canonical_config._config)
    elif len(arguments) == 1:
        conf_path = arguments[0]
        configuration = Configuration.load(conf_path, options.schema_path)
    else:
        parser.error('Too many arguments.')
        # Does not return.
    configuration.list_config(
        verbose=options.verbose, section_name=options.section_name)


if __name__ == '__main__':
    sys.exit(main())
