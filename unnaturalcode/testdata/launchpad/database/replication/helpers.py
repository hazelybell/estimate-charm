# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Common helpers for replication scripts."""

__metaclass__ = type
__all__ = []

import subprocess
from tempfile import NamedTemporaryFile
from textwrap import dedent

import psycopg2

from lp.services.config import config
from lp.services.database.postgresql import (
    all_sequences_in_schema,
    all_tables_in_schema,
    ConnectionString,
    fqn,
    )
from lp.services.database.sqlbase import (
    connect,
    ISOLATION_LEVEL_DEFAULT,
    sqlvalues,
    )
from lp.services.scripts.logger import (
    DEBUG2,
    log,
    )

# The Slony-I clustername we use with Launchpad. Hardcoded because there
# is no point changing this, ever.
CLUSTERNAME = 'sl'

# The namespace in the database used to contain all the Slony-I tables.
CLUSTER_NAMESPACE = '_%s' % CLUSTERNAME

# Replication set id constants. Don't change these without DBA help.
LPMAIN_SET_ID = 1
HOLDING_SET_ID = 666
SSO_SET_ID = 3
LPMIRROR_SET_ID = 4

# Seed tables for the lpmain replication set to be passed to
# calculate_replication_set().
LPMAIN_SEED = frozenset([
    ('public', 'account'),
    ('public', 'person'),
    ('public', 'databasereplicationlag'),
    ('public', 'fticache'),
    ('public', 'nameblacklist'),
    ('public', 'openidconsumerassociation'),
    ('public', 'openidconsumernonce'),
    ('public', 'codeimportmachine'),
    ('public', 'scriptactivity'),
    ('public', 'launchpadstatistic'),
    ('public', 'parsedapachelog'),
    ('public', 'databasereplicationlag'),
    ('public', 'featureflag'),
    ('public', 'bugtaskflat'),
    # suggestivepotemplate can be removed when the
    # suggestivepotemplate.potemplate foreign key constraint exists on
    # production.
    ('public', 'suggestivepotemplate'),
    # These are odd. They are updated via slonik & EXECUTE SCRIPT, and
    # the contents of these tables will be different on each node
    # because we store timestamps when the patches were applied.
    # However, we want the tables listed as replicated so that, when
    # building a new replica, the data that documents the schema patch
    # level matches the schema patch level and upgrade.py does the right
    # thing. This is a bad thing to do, but we are safe in this
    # particular case.
    ('public', 'launchpaddatabaserevision'),
    ('public', 'launchpaddatabaseupdatelog'),
    ])

# Explicitly list tables that should not be replicated. This includes the
# session tables, as these might exist in developer databases but will not
# exist in the production launchpad database.
IGNORED_TABLES = set([
    # Session tables that in some situations will exist in the main lp
    # database.
    'public.secret', 'public.sessiondata', 'public.sessionpkgdata',
    # Mirror tables, per Bug #489078. These tables have their own private
    # replication set that is setup manually.
    'public.lp_account',
    'public.lp_openididentifier',
    'public.lp_person',
    'public.lp_personlocation',
    'public.lp_teamparticipation',
    # Database statistics
    'public.databasetablestats',
    'public.databasecpustats',
    'public.databasediskutilization',
    # Don't replicate OAuthNonce - too busy and no real gain.
    'public.oauthnonce',
    # Ubuntu SSO database. These tables where created manually by ISD
    # and the Launchpad scripts should not mess with them. Eventually
    # these tables will be in a totally separate database.
    'public.auth_permission',
    'public.auth_group',
    'public.auth_user',
    'public.auth_message',
    'public.django_content_type',
    'public.auth_permission',
    'public.django_session',
    'public.django_site',
    'public.django_admin_log',
    'public.ssoopenidrpconfig',
    'public.auth_group_permissions',
    'public.auth_user_groups',
    'public.auth_user_user_permissions',
    'public.oauth_nonce',
    'public.oauth_consumer',
    'public.oauth_token',
    'public.api_user',
    'public.oauth_consumer_id_seq',
    'public.api_user_id_seq',
    'public.oauth_nonce_id_seq',
    ])

# Calculate IGNORED_SEQUENCES
IGNORED_SEQUENCES = set('%s_id_seq' % table for table in IGNORED_TABLES)


def slony_installed(con):
    """Return True if the connected database is part of a Launchpad Slony-I
    cluster.
    """
    cur = con.cursor()
    cur.execute("""
        SELECT TRUE FROM pg_class,pg_namespace
        WHERE
            nspname = %s
            AND relname = 'sl_table'
            AND pg_class.relnamespace = pg_namespace.oid
        """ % sqlvalues(CLUSTER_NAMESPACE))
    return cur.fetchone() is not None


class TableReplicationInfo:
    """Internal table replication details."""
    table_id = None
    replication_set_id = None
    master_node_id = None

    def __init__(self, con, namespace, table_name):
        cur = con.cursor()
        cur.execute("""
            SELECT tab_id, tab_set, set_origin
            FROM %s.sl_table, %s.sl_set
            WHERE tab_set = set_id
                AND tab_nspname = %s
                AND tab_relname = %s
            """ % (
                (CLUSTER_NAMESPACE, CLUSTER_NAMESPACE)
                + sqlvalues(namespace, table_name)))
        row = cur.fetchone()
        if row is None:
            raise LookupError(fqn(namespace, table_name))
        self.table_id, self.replication_set_id, self.master_node_id = row


def sync(timeout, exit_on_fail=True):
    """Generate a sync event and wait for it to complete on all nodes.

    This means that all pending events have propagated and are in sync
    to the point in time this method was called. This might take several
    hours if there is a large backlog of work to replicate.

    :param timeout: Number of seconds to wait for the sync. 0 to block
                    indefinitely.

    :param exit_on_fail: If True, on failure of the sync
                         SystemExit is raised using the slonik return code.

    :returns: True if the sync completed successfully. False if
              exit_on_fail is False and the script failed for any reason.
    """
    return execute_slonik("", sync=timeout, exit_on_fail=exit_on_fail)


def execute_slonik(script, sync=None, exit_on_fail=True, auto_preamble=True):
    """Use the slonik command line tool to run a slonik script.

    :param script: The script as a string. Preamble should not be included.

    :param sync: Number of seconds to wait for sync before failing. 0 to
                 block indefinitely.

    :param exit_on_fail: If True, on failure of the slonik script
                         SystemExit is raised using the slonik return code.

    :param auto_preamble: If True, the generated preamble will be
                          automatically included.

    :returns: True if the script completed successfully. False if
              exit_on_fail is False and the script failed for any reason.
    """

    # Add the preamble and optional sync to the script.
    if auto_preamble:
        script = preamble() + script

    if sync is not None:
        sync_script = dedent("""\
            sync (id = @master_node);
            wait for event (
                origin = @master_node, confirmed = ALL,
                wait on = @master_node, timeout = %d);
            """ % sync)
        script = script + sync_script

    # Copy the script to a NamedTemporaryFile rather than just pumping it
    # to slonik via stdin. This way it can be examined if slonik appears
    # to hang.
    script_on_disk = NamedTemporaryFile(prefix="slonik", suffix=".sk")
    print >> script_on_disk, script
    script_on_disk.flush()

    # Run slonik
    log.debug("Executing slonik script %s" % script_on_disk.name)
    log.log(DEBUG2, 'Running script:\n%s' % script)
    returncode = subprocess.call(['slonik', script_on_disk.name])

    if returncode != 0:
        log.error("slonik script failed")
        if exit_on_fail:
            raise SystemExit(1)

    return returncode == 0


class Node:
    """Simple data structure for holding information about a Slony node."""
    def __init__(self, node_id, nickname, connection_string, is_master):
        self.node_id = node_id
        self.nickname = nickname
        self.connection_string = connection_string
        self.is_master = is_master

    def connect(self, isolation=ISOLATION_LEVEL_DEFAULT):
        con = psycopg2.connect(str(self.connection_string))
        con.set_isolation_level(isolation)
        return con


def _get_nodes(con, query):
    """Return a list of Nodes."""
    if not slony_installed(con):
        return []
    cur = con.cursor()
    cur.execute(query)
    nodes = []
    for node_id, nickname, connection_string, is_master in cur.fetchall():
        nodes.append(Node(node_id, nickname, connection_string, is_master))
    return nodes


def get_master_node(con, set_id=1):
    """Return the master Node, or None if the cluster is still being setup."""
    nodes = _get_nodes(con, """
        SELECT DISTINCT
            set_origin AS node_id,
            'master',
            pa_conninfo AS connection_string,
            True
        FROM _sl.sl_set
        LEFT OUTER JOIN _sl.sl_path ON set_origin = pa_server
        WHERE set_id = %d
        """ % set_id)
    if not nodes:
        return None
    assert len(nodes) == 1, "More than one master found for set %s" % set_id
    return nodes[0]


def get_slave_nodes(con, set_id=1):
    """Return the list of slave Nodes."""
    return _get_nodes(con, """
        SELECT DISTINCT
            pa_server AS node_id,
            'slave' || pa_server,
            pa_conninfo AS connection_string,
            False
        FROM _sl.sl_set
        JOIN _sl.sl_subscribe ON set_id = sub_set
        JOIN _sl.sl_path ON sub_receiver = pa_server
        WHERE
            set_id = %d
        ORDER BY node_id
        """ % set_id)


def get_nodes(con, set_id=1):
    """Return a list of all Nodes."""
    master_node = get_master_node(con, set_id)
    if master_node is None:
        return []
    else:
        return [master_node] + get_slave_nodes(con, set_id)


def get_all_cluster_nodes(con):
    """Return a list of all Nodes in the cluster.

    node.is_master will be None, as this boolean doesn't make sense
    in the context of a cluster rather than a single replication set.
    """
    if not slony_installed(con):
        return []
    nodes = _get_nodes(con, """
        SELECT DISTINCT
            pa_server AS node_id,
            'node' || pa_server || '_node',
            pa_conninfo AS connection_string,
            NULL
        FROM _sl.sl_path
        ORDER BY node_id
        """)
    if not nodes:
        # There are no subscriptions yet, so no paths. Generate the
        # master Node.
        cur = con.cursor()
        cur.execute("SELECT no_id from _sl.sl_node")
        node_ids = [row[0] for row in cur.fetchall()]
        if len(node_ids) == 0:
            return []
        assert len(node_ids) == 1, "Multiple nodes but no paths."
        master_node_id = node_ids[0]
        master_connection_string = ConnectionString(
            config.database.rw_main_master)
        master_connection_string.user = 'slony'
        return [Node(
            master_node_id, 'node%d_node' % master_node_id,
            master_connection_string, True)]
    return nodes


def preamble(con=None):
    """Return the preable needed at the start of all slonik scripts."""

    if con is None:
        con = connect(user='slony')

    master_node = get_master_node(con)
    nodes = get_all_cluster_nodes(con)
    if master_node is None and len(nodes) == 1:
        master_node = nodes[0]

    preamble = [dedent("""\
        #
        # Every slonik script must start with a clustername, which cannot
        # be changed once the cluster is initialized.
        #
        cluster name = sl;

        # Symbolic ids for replication sets.
        define lpmain_set   %d;
        define holding_set  %d;
        define sso_set      %d;
        define lpmirror_set %d;
        """ % (LPMAIN_SET_ID, HOLDING_SET_ID, SSO_SET_ID, LPMIRROR_SET_ID))]

    if master_node is not None:
        preamble.append(dedent("""\
        # Symbolic id for the main replication set master node.
        define master_node %d;
        define master_node_conninfo '%s';
        """ % (master_node.node_id, master_node.connection_string)))

    for node in nodes:
        preamble.append(dedent("""\
            define %s %d;
            define %s_conninfo '%s';
            node @%s admin conninfo = @%s_conninfo;
            """ % (
                node.nickname, node.node_id,
                node.nickname, node.connection_string,
                node.nickname, node.nickname)))

    return '\n\n'.join(preamble)


def calculate_replication_set(cur, seeds):
    """Return the minimal set of tables and sequences needed in a
    replication set containing the seed table.

    A replication set must contain all tables linked by foreign key
    reference to the given table, and sequences used to generate keys.
    Tables and sequences can be added to the IGNORED_TABLES and
    IGNORED_SEQUENCES lists for cases where we known can safely ignore
    this restriction.

    :param seeds: [(namespace, tablename), ...]

    :returns: (tables, sequences)
    """
    # Results
    tables = set()
    sequences = set()

    # Our pending set to check
    pending_tables = set(seeds)

    # Generate the set of tables that reference the seed directly
    # or indirectly via foreign key constraints, including the seed itself.
    while pending_tables:
        namespace, tablename = pending_tables.pop()

        # Skip if the table doesn't exist - we might have seeds listed that
        # have been removed or are yet to be created.
        cur.execute("""
            SELECT TRUE
            FROM pg_class, pg_namespace
            WHERE pg_class.relnamespace = pg_namespace.oid
                AND pg_namespace.nspname = %s
                AND pg_class.relname = %s
            """ % sqlvalues(namespace, tablename))
        if cur.fetchone() is None:
            log.debug("Table %s.%s doesn't exist" % (namespace, tablename))
            continue

        tables.add((namespace, tablename))

        # Find all tables that reference the current (seed) table
        # and all tables that the seed table references.
        cur.execute("""
            SELECT ref_namespace.nspname, ref_class.relname
            FROM
                -- One of the seed tables
                pg_class AS seed_class,
                pg_namespace AS seed_namespace,

                -- A table referencing the seed, or being referenced by
                -- the seed.
                pg_class AS ref_class,
                pg_namespace AS ref_namespace,

                pg_constraint
            WHERE
                seed_class.relnamespace = seed_namespace.oid
                AND ref_class.relnamespace = ref_namespace.oid

                AND seed_namespace.nspname = %s
                AND seed_class.relname = %s

                -- Foreign key constraints are all we care about.
                AND pg_constraint.contype = 'f'

                -- We want tables referenced by, or referred to, the
                -- seed table.
                AND ((pg_constraint.conrelid = ref_class.oid
                        AND pg_constraint.confrelid = seed_class.oid)
                    OR (pg_constraint.conrelid = seed_class.oid
                        AND pg_constraint.confrelid = ref_class.oid)
                    )
            """ % sqlvalues(namespace, tablename))
        for namespace, tablename in cur.fetchall():
            key = (namespace, tablename)
            if (key not in tables and key not in pending_tables
                and '%s.%s' % (namespace, tablename) not in IGNORED_TABLES):
                pending_tables.add(key)

    # Generate the set of sequences that are linked to any of our set of
    # tables. We assume these are all sequences created by creation of
    # serial or bigserial columns, or other sequences OWNED BY a particular
    # column.
    for namespace, tablename in tables:
        cur.execute("""
            SELECT seq
            FROM (
                SELECT pg_get_serial_sequence(%s, attname) AS seq
                FROM pg_namespace, pg_class, pg_attribute
                WHERE pg_namespace.nspname = %s
                    AND pg_class.relnamespace = pg_namespace.oid
                    AND pg_class.relname = %s
                    AND pg_attribute.attrelid = pg_class.oid
                    AND pg_attribute.attisdropped IS FALSE
                ) AS whatever
            WHERE seq IS NOT NULL;
            """ % sqlvalues(fqn(namespace, tablename), namespace, tablename))
        for sequence, in cur.fetchall():
            if sequence not in IGNORED_SEQUENCES:
                sequences.add(sequence)

    # We can't easily convert the sequence name to (namespace, name) tuples,
    # so we might as well convert the tables to dot notation for consistancy.
    tables = set(fqn(namespace, tablename) for namespace, tablename in tables)

    return tables, sequences


def discover_unreplicated(cur):
    """Inspect the database for tables and sequences in the public schema
    that are not in a replication set.

    :returns: (unreplicated_tables_set, unreplicated_sequences_set)
    """
    all_tables = all_tables_in_schema(cur, 'public')
    all_sequences = all_sequences_in_schema(cur, 'public')

    # Ignore any tables and sequences starting with temp_. These are
    # transient and not to be replicated per Bug #778338.
    all_tables = set(
        table for table in all_tables
            if not table.startswith('public.temp_'))
    all_sequences = set(
        sequence for sequence in all_sequences
            if not sequence.startswith('public.temp_'))

    cur.execute("""
        SELECT tab_nspname, tab_relname FROM %s
        WHERE tab_nspname = 'public'
        """ % fqn(CLUSTER_NAMESPACE, "sl_table"))
    replicated_tables = set(fqn(*row) for row in cur.fetchall())

    cur.execute("""
        SELECT seq_nspname, seq_relname FROM %s
        WHERE seq_nspname = 'public'
        """ % fqn(CLUSTER_NAMESPACE, "sl_sequence"))
    replicated_sequences = set(fqn(*row) for row in cur.fetchall())

    return (
        all_tables - replicated_tables - IGNORED_TABLES,
        all_sequences - replicated_sequences - IGNORED_SEQUENCES)


class ReplicationConfigError(Exception):
    """Exception raised by validate_replication_sets() when our replication
    setup is misconfigured.
    """


def validate_replication(cur):
    """Raise a ReplicationSetupError if there is something wrong with
    our replication sets.

    This might include tables exist that are not in a replication set,
    or tables that exist in multiple replication sets for example.

    These is not necessarily limits with what Slony-I allows, but might
    be due to policies we have made (eg. a table allowed in just one
    replication set).
    """
    unrepl_tables, unrepl_sequences = discover_unreplicated(cur)
    if unrepl_tables:
        raise ReplicationConfigError(
            "Unreplicated tables: %s" % repr(unrepl_tables))
    if unrepl_sequences:
        raise ReplicationConfigError(
            "Unreplicated sequences: %s" % repr(unrepl_sequences))

    lpmain_tables, lpmain_sequences = calculate_replication_set(
        cur, LPMAIN_SEED)
