= Launchpad configs =

This directory defines the configurations used to run Launchpad
applications in specific environments.


== Environments ==

This directory stores configs. The config used is selected on startup
using the LPCONFIG environment variable.

Each config directory contains a launchpad-lazr.conf file, and optionally
a number of .zcml files. These .zcml files are processed as ZCML
overrides allowing you to change behavior not yet configurable in
launchpad-lazr.conf.

If you want to create a temporary config, prefix the directory name with
'+' so that bzr ignores it and you won't accidentally commit it (this
pattern is listed in the top level .bzrignore in this tree).

If you need to make changes to the production, staging or dogfood configs
make sure you inform the people in charge of those systems. You may wish
to do this if you are adding a new required config option to
launchpad-lazr.conf.

The old ZConfig-based launchpad.conf files are still used to define
servers and log files. These will be replaced when lazr.config is
bootstrapped into the Zope startup process.


== LaunchpadConfig ==

Launchpad uses a singleton LaunchpadConfig object to select the config
to load and manage its state.


=== Instance directories and process files ===

The directories in configs/ represent environment's config `instance`.
Environment and instance are synonymous in this case. The instance is
often set by the LPCONFIG environment variable, but an app may override
this. The test.py calls:

    config.setInstance('testrunner')

to force the testrunner configuration to be loaded.

An instance directory may contain several lazr.config conf files.
LaunchpadConfig loads the config file named for the process that is
running, eg. if the processes name is 'test', LaunchpadConfig looks for
test-lazr.conf. launchpad-lazr.conf is loaded if not a lazr config files
named for the process.

All this information is available in the config object.

    >>> config.instance_name
    'testrunner'
    >>> config.process_name
    'test'

    >>> config.filename
    '.../configs/testrunner/launchpad-lazr.conf'
    >>> config.extends.filename
    '.../configs/development/launchpad-lazr.conf'


=== Accessing the LaunchpadConfig in code ===

The LaunchpadConfig singleton is exposed as config in its module.

    from lp.services.config import config

The config can be accessed as a dictionary...

    >>> 'launchpad' in config
    True

    >>> config['launchpad']['default_batch_size']
    5

...though it is commonly accessed as an object.

    >>> config.librarian.download_host
    'localhost'

    >>> config.librarian.download_port
    58000

You can learn more about lp.services.config in the doctest located at

    lib/canonical/launchpad/doc/canonical-config.txt


=== Testing with LaunchpadConfig ===

Configurations are meant to be immutable--applications should never
alter the config. Nor should tests. Older code and tests assumed
that because the keys looked like attributes of the config, they
could be set. This was *wrong*. The code was actually adding an
attribute to the LaunchpadConfig instance rather that updating to
underlying config object. While the code intended to reset the key's
value to the original value, it would have to delete the new attribute
to really restore the config singleton.

LaunchpadConfig supports testing by exposing lazr.config's push() and
pop() methods to add and remove configurations to the stack of
ConfigData. The configuration can be modified and safely restored.

Tests can call push() with the configuration name and data to update
the config singleton.

    >>> test_data = ("""
    ...     [answertracker]
    ...     email_domain: answers.launchpad.dev""")
    >>> config.push('test_data', test_data)
    >>> config.answertracker.email_domain
    'answers.launchpad.dev'

And tests can remove the data with pop() when they are done to restore
the config.

    >>> config.pop('test_data')
    (<canonical.lazr.config.ConfigData ...>,)
    >>> config.answertracker.email_domain
    'answers.launchpad.net'


== lazr.conf schema and confs ==

All Launchpad configs inherit from the Launchpad schema defined
in ../lib/lp/services/config/schema-lazr.conf (it is symlinked
as ./schema-lazr.conf for convenience).

lazr.config conf and schema files look like ini-based conf files, but
supports a number of features that make it easy for us to run multiple
versions of the application:

    1. The [meta] section's extends: key points to a file that defines
       the inherited sections, keys, and values.
    2. All config automatically inherit the default sections and
       key values from the schema. configs need only to define
       the keys that are unique to itself. Shared confs can be created
       to define a common set of key values for many configs.
    3. Except for optional sections ([<section>.optional]) which must
       be declared in a conf file for all the keys and values to be
       inherited.
    4. Schema's may define a template for a category of sections
       ([<category>.template]) to define a common set of keys and
       values.
    5. The schema and configs are validated. Configs cannot add
       sections or keys that are not defined in the schema. Sections
       and keys cannot be defined twice in a file.
    6. Launchpad uses implicit typing. The default value of a key is a
       str. If the vales looks like a int, it will be cast as an int.
       the tokens 'true', 'false', and 'none' (in any case) will map
       to Python types.

When adding sections and keys to the schema, include a comment that
documents their purpose.

The schema should define the default value for a key when the value is
safe for all environments. Values that enable a common feature, or set
the size of a list for example, should be in the schema. Values like
cause email to be sent, or development features should be disabled
in the schema--each environment that wants the enabled feature may do
so in its local conf file.

You can learn more about lazr.config in the doctest located at

    lib/canonical/lazr/doc/config.txt


=== schema template and optional sections ===

The schema can contain [<category>.template] sections that define a
common set of keys and default value for category of sections.
For example:

    [vhost.template]
    # Host name of this virtual host.
    # This is matched from the incoming Host header, and
    # also used to put together URLs if rooturl is not provided.
    # Example: launchpad.net
    # datatype: string
    hostname: none

    # Alternative host names to match, in addition to
    # the one given in hostname, comma separated.
    # Example: wwwww.launchpad.net, www.launchpad.net
    # datatype: string
    althostnames: none

    # Explicit root URL for this virtual host.
    # If this is not provided, the root URL is calculated
    # based on the host name.
    # Example: https://launchpad.net/
    # datatype: string
    rooturl: none

The [vhost.template] defines the keys and default values of a vhost.
"vhost" is a category, any section whose name is prefixed "vhost" will
inherit the keys and default values of the [vhost.template].

[vhost.answers] is an empty section in the schema...

    [vhost.answers]

...and lpnet-lazr.conf defines this:

    [vhost.answers]
    hostname: answers.launchpad.net

./lpnet1/launchpad-lazr.conf does not define anything for
[vhost.answers], yet when it is loaded, it has the all the keys and
default values of [vhost.template] from the schema, with the hostname
change defined in lpnet-lazr.conf:

    [vhost.answers]
    althostnames: None
    hostname: answers.launchpad.net
    rooturl: None

The schema may contain [<section>.optional] to define a section
that may declared in a conf, but is not automatically
inherited. This allows the application to define process configuration
data without exposing that information in every environment.
For example:

    [vhost.xmlrpc_private.optional]

is defined in the schema. It has the default keys and values defined
in [vhost.template]. The [vhost.xmlrpc_private] is not visible in
most confs because they do not declare that they use the section.
The production-xmlrpc-private/launchpad-lazr.conf file does though,
by including [vhost.xmlrpc_private] section:

    [vhost.xmlrpc_private]
    hostname: xmlrpc.lp.internal
    rooturl: https://launchpad.net/

Including just the section ([vhost.xmlrpc_private]) will suffice. In
this case, the two keys were redefined.


=== Implicit typing ===

lazr.config support implicit typing so that the application does not
need to coerce the config values:

    Integers: any value that is only made up of numbers, optionally
        prefixed with +/- is cast as an int: 0, 2001, -55, +404, 100.

    True, False, or None: any value that matches the boolean and None
        keywords is treated as the prescribed type. The match is
        case-insensitive: none, nOne, true, and False are all matched.

    Strings: any value that is not an int, bool, or None is treated as
        a str. Multi-line strings can be included by indenting the
        continuation lines to show that they are subordinate to the
        key:

            mykey: this line
                has a line break in it.

Implicit typing does not support lists, or compound types. Code must
split and unpack the value to make the desired object. For example,
the callsite must split the host:port compound object and coerce the
port to an int.


=== Config inheritance ===

The lazr configurations in this directory descend from the
Launchpad schema. This is a general outline of inheritance:

    ../lib/lp/services/config/schema-lazr.conf
        |
        + development/launchpad-lazr.conf
        |    |
        |    + testrunner/launchpad-lazr.conf
        |         |
        |         + authserver-lazr.conf
        |         |
        |         + testrunner_\d+/launchpad-lazr.conf
        |         |
        |         + testrunner-appserver/launchpad-lazr.conf
        |             |
        |             + authserver-lazr.conf
        |             |
        |             + testrunner-appserver_\d+/launchpad-lazr.conf
        |
        + staging-lazr.conf
        |    |
        |    + bazaar-staging/launchpad-lazr.conf
        |    |
        |    + staging/launchpad-lazr.conf
        |    |    |
        |    |    + authserver-lazr.conf
        |    |
        |    + staging-mailman/launchpad-lazr.conf
        |
        + lpnet-lazr.conf
        |    |
        |    + lpnet<1-8>/launchpad-lazr.conf
        |    |
        |    + wildcherry/launchpad-lazr.conf
        |    |
        |    + librarian/launchpad-lazr.conf
        |    |
        |    + librarian-restricted/launchpad-lazr.conf
        |    |
        |    + production/launchpad-lazr.conf
        |    |
        |    + production-mailman/launchpad-lazr.conf
        |    |
        |    + production-xmlrpc-private/launchpad-lazr.conf
        |
        + demo-lazr.conf
        |    |
        |    + demo<1-4>/launchpad-lazr.conf
        |
        + beta-lazr.conf
        |    |
        |    + beta<1-3>/launchpad-lazr.conf
        |
        + dogfood/launchpad-lazr.conf
        |
        + ...

There are other configuration in this directory that are not
listed here


=== Viewing a configuration with lsconf.py ===

You can view the complete configuration for an process using the
lsconf.py utility to assemble the configuration from the lazr
conf file. eg:

    ./utilities/lsconf.py ./configs/production/launchpad-lazr.conf

The output looks like a lazr.conf file that lists all the sections
and keys in the configuration. The heading lists the order the conf
files were processed from child to ancestor.

Two useful options are -v and -s. The verbose option (-v) will annotate
each key with a comment explaining which conf file set the value.
The section name option (-s) will limit the output to the named
section. eg:

    ./utilities/lsconf.py -v -s answertracker \
        ./configs/production/launchpad-lazr.conf

    # This configuration derives from:
    #     ./configs/production/launchpad-lazr.conf
    #     ./configs/lpnet-lazr.conf
    #     ./lib/lp/services/config/schema-lazr.conf

    [answertracker]
    # Defined in: lib/lp/services/config/schema-lazr.conf
    days_before_expiration: 15

    # Defined in: lib/lp/services/config/schema-lazr.conf
    dbuser: answertracker

    # Defined in: lib/lp/services/config/schema-lazr.conf
    email_domain: answers.launchpad.net

