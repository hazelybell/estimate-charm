# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Launchpad test fixtures that have no better home."""

__metaclass__ = type
__all__ = [
    'CaptureOops',
    'DemoMode',
    'DisableTriggerFixture',
    'PGBouncerFixture',
    'PGNotReadyError',
    'Urllib2Fixture',
    'ZopeAdapterFixture',
    'ZopeEventHandlerFixture',
    'ZopeViewReplacementFixture',
    ]

from ConfigParser import SafeConfigParser
import os.path
import socket
import time

import amqplib.client_0_8 as amqp
from fixtures import (
    EnvironmentVariableFixture,
    Fixture,
    )
from lazr.restful.utils import get_current_browser_request
import oops
import oops_amqp
import pgbouncer.fixture
from wsgi_intercept import (
    add_wsgi_intercept,
    remove_wsgi_intercept,
    )
from wsgi_intercept.urllib2_intercept import (
    install_opener,
    uninstall_opener,
    )
from zope.component import (
    adapter,
    getGlobalSiteManager,
    provideHandler,
    )
from zope.interface import Interface
from zope.publisher.interfaces.browser import IDefaultBrowserLayer
from zope.security.checker import (
    defineChecker,
    getCheckerForInstancesOf,
    undefineChecker,
    )

from lp.services import webapp
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.librarian.model import LibraryFileAlias
from lp.services.messaging.interfaces import MessagingUnavailable
from lp.services.messaging.rabbit import connect
from lp.services.timeline.requesttimeline import get_request_timeline
from lp.services.webapp.errorlog import ErrorReportEvent
from lp.testing.dbuser import dbuser


class PGNotReadyError(Exception):
    pass


class PGBouncerFixture(pgbouncer.fixture.PGBouncerFixture):
    """Inserts a controllable pgbouncer instance in front of PostgreSQL.

    The pgbouncer proxy can be shutdown and restarted at will, simulating
    database outages and fastdowntime deployments.
    """

    def __init__(self):
        super(PGBouncerFixture, self).__init__()

        # Known databases
        from lp.testing.layers import DatabaseLayer
        dbnames = [
            DatabaseLayer._db_fixture.dbname,
            DatabaseLayer._db_template_fixture.dbname,
            'session_ftest',
            'launchpad_empty',
            ]
        for dbname in dbnames:
            self.databases[dbname] = 'dbname=%s port=5432 host=localhost' % (
                dbname,)

        # Known users, pulled from security.cfg
        security_cfg_path = os.path.join(
            config.root, 'database', 'schema', 'security.cfg')
        security_cfg_config = SafeConfigParser({})
        security_cfg_config.read([security_cfg_path])
        for section_name in security_cfg_config.sections():
            self.users[section_name] = 'trusted'
            self.users[section_name + '_ro'] = 'trusted'
        self.users[os.environ['USER']] = 'trusted'
        self.users['pgbouncer'] = 'trusted'

        # Administrative access is useful for debugging.
        self.admin_users = ['launchpad', 'pgbouncer', os.environ['USER']]

    def setUp(self):
        super(PGBouncerFixture, self).setUp()

        # reconnect_store cleanup added first so it is run last, after
        # the environment variables have been reset.
        self.addCleanup(self._maybe_reconnect_stores)

        # Abuse the PGPORT environment variable to get things connecting
        # via pgbouncer. Otherwise, we would need to temporarily
        # overwrite the database connection strings in the config.
        self.useFixture(EnvironmentVariableFixture('PGPORT', str(self.port)))

        # Reset database connections so they go through pgbouncer.
        self._maybe_reconnect_stores()

    def _maybe_reconnect_stores(self):
        """Force Storm Stores to reconnect if they are registered.

        This is a noop if the Component Architecture is not loaded,
        as we are using a test layer that doesn't provide database
        connections.
        """
        from lp.testing.layers import (
            reconnect_stores,
            is_ca_available,
            )
        if is_ca_available():
            reconnect_stores()

    def start(self, retries=20, sleep=0.5):
        """Start PGBouncer, waiting for it to accept connections if neccesary.
        """
        super(PGBouncerFixture, self).start()
        for i in xrange(retries):
            try:
                socket.create_connection((self.host, self.port))
            except socket.error:
                # Try again.
                pass
            else:
                break
            time.sleep(sleep)
        else:
            raise PGNotReadyError("Not ready after %d attempts." % retries)


class ZopeAdapterFixture(Fixture):
    """A fixture to register and unregister an adapter."""

    def __init__(self, *args, **kwargs):
        self._args, self._kwargs = args, kwargs

    def setUp(self):
        super(ZopeAdapterFixture, self).setUp()
        site_manager = getGlobalSiteManager()
        site_manager.registerAdapter(
            *self._args, **self._kwargs)
        self.addCleanup(
            site_manager.unregisterAdapter,
            *self._args, **self._kwargs)


class ZopeEventHandlerFixture(Fixture):
    """A fixture that provides and then unprovides a Zope event handler."""

    def __init__(self, handler):
        super(ZopeEventHandlerFixture, self).__init__()
        self._handler = handler

    def setUp(self):
        super(ZopeEventHandlerFixture, self).setUp()
        gsm = getGlobalSiteManager()
        provideHandler(self._handler)
        self.addCleanup(gsm.unregisterHandler, self._handler)


class ZopeViewReplacementFixture(Fixture):
    """A fixture that allows you to temporarily replace one view with another.

    This will not work with the AppServerLayer.
    """

    def __init__(self, name, context_interface,
                 request_interface=IDefaultBrowserLayer,
                 replacement=None):
        super(ZopeViewReplacementFixture, self).__init__()
        self.name = name
        self.context_interface = context_interface
        self.request_interface = request_interface
        self.gsm = getGlobalSiteManager()
        # It can be convenient--bordering on necessary--to use this original
        # class as a base for the replacement.
        self.original = self.gsm.adapters.registered(
            (context_interface, request_interface), Interface, name)
        self.checker = getCheckerForInstancesOf(self.original)
        if self.original is None:
            # The adapter registry does not provide good methods to introspect
            # it. If it did, we might try harder here.
            raise ValueError(
                'No existing view to replace.  Wrong request interface?  '
                'Try a layer.')
        self.replacement = replacement

    def setUp(self):
        super(ZopeViewReplacementFixture, self).setUp()
        if self.replacement is None:
            raise ValueError('replacement is not set')
        self.gsm.adapters.register(
            (self.context_interface, self.request_interface), Interface,
             self.name, self.replacement)
        # The same checker should be sufficient.  If it ever isn't, we
        # can add more flexibility then.
        defineChecker(self.replacement, self.checker)

        self.addCleanup(
            undefineChecker, self.replacement)
        self.addCleanup(
            self.gsm.adapters.register,
            (self.context_interface, self.request_interface),
            Interface,
            self.name, self.original)


class ZopeUtilityFixture(Fixture):
    """A fixture that temporarily registers a different utility."""

    def __init__(self, component, intf, name):
        """Construct a new fixture.

        :param component: An instance of a class that provides this
            interface.
        :param intf: The Zope interface class to register, eg
            IMailDelivery.
        :param name: A string name to match.
        """
        self.component = component
        self.name = name
        self.intf = intf

    def setUp(self):
        super(ZopeUtilityFixture, self).setUp()
        gsm = getGlobalSiteManager()
        gsm.registerUtility(self.component, self.intf, self.name)
        self.addCleanup(
            gsm.unregisterUtility,
            self.component, self.intf, self.name)


class Urllib2Fixture(Fixture):
    """Let tests use urllib to connect to an in-process Launchpad.

    Initially this only supports connecting to launchpad.dev because
    that is all that is needed.  Later work could connect all
    sub-hosts (e.g. bugs.launchpad.dev)."""

    def setUp(self):
        # Work around circular import.
        from lp.testing.layers import wsgi_application
        super(Urllib2Fixture, self).setUp()
        add_wsgi_intercept('launchpad.dev', 80, lambda: wsgi_application)
        self.addCleanup(remove_wsgi_intercept, 'launchpad.dev', 80)
        install_opener()
        self.addCleanup(uninstall_opener)


class CaptureOops(Fixture):
    """Capture OOPSes notified via zope event notification.

    :ivar oopses: A list of the oops objects raised while the fixture is
        setup.
    :ivar oops_ids: A set of observed oops ids. Used to de-dup reports
        received over AMQP.
    """

    AMQP_SENTINEL = "STOP NOW"

    def setUp(self):
        super(CaptureOops, self).setUp()
        self.oopses = []
        self.oops_ids = set()
        self.useFixture(ZopeEventHandlerFixture(self._recordOops))
        try:
            self.connection = connect()
        except MessagingUnavailable:
            self.channel = None
        else:
            self.addCleanup(self.connection.close)
            self.channel = self.connection.channel()
            self.addCleanup(self.channel.close)
            self.oops_config = oops.Config()
            self.oops_config.publishers.append(self._add_oops)
            self.setUpQueue()

    def setUpQueue(self):
        """Sets up the queue to be used to receive reports.

        The queue is autodelete which means we can only use it once: after
        that it will be automatically nuked and must be recreated.
        """
        self.queue_name, _, _ = self.channel.queue_declare(
            durable=True, auto_delete=True)
        # In production the exchange already exists and is durable, but
        # here we make it just-in-time, and tell it to go when the test
        # fixture goes.
        self.channel.exchange_declare(config.error_reports.error_exchange,
            "fanout", durable=True, auto_delete=True)
        self.channel.queue_bind(
            self.queue_name, config.error_reports.error_exchange)

    def _add_oops(self, report):
        """Add an oops if it isn't already recorded.

        This is called from both amqp and in-appserver situations.
        """
        if report['id'] not in self.oops_ids:
            self.oopses.append(report)
            self.oops_ids.add(report['id'])

    @adapter(ErrorReportEvent)
    def _recordOops(self, event):
        """Callback from zope publishing to publish oopses."""
        self._add_oops(event.object)

    def sync(self):
        """Sync the in-memory list of OOPS with the external OOPS source."""
        if not self.channel:
            return
        # Send ourselves a message: when we receive this, we've processed all
        # oopses created before sync() was invoked.
        message = amqp.Message(self.AMQP_SENTINEL)
        # Match what oops publishing does
        message.properties["delivery_mode"] = 2
        # Publish the message via a new channel (otherwise rabbit
        # shortcircuits it straight back to us, apparently).
        connection = connect()
        try:
            channel = connection.channel()
            try:
                channel.basic_publish(
                    message, config.error_reports.error_exchange,
                    config.error_reports.error_queue_key)
            finally:
                channel.close()
        finally:
            connection.close()
        receiver = oops_amqp.Receiver(
            self.oops_config, connect, self.queue_name)
        receiver.sentinel = self.AMQP_SENTINEL
        try:
            receiver.run_forever()
        finally:
            # Ensure we leave the queue ready to roll, or later calls to
            # sync() will fail.
            self.setUpQueue()


class CaptureTimeline(Fixture):
    """Record and return the timeline.

    This won't work well (yet) for code that starts new requests as they will
    reset the timeline.
    """

    def setUp(self):
        Fixture.setUp(self)
        webapp.adapter.set_request_started(time.time())
        self.timeline = get_request_timeline(
            get_current_browser_request())
        self.addCleanup(webapp.adapter.clear_request_started)


class DemoMode(Fixture):
    """Run with an is_demo configuration.

    This changes the page styling, feature flag permissions, and perhaps
    other things.
    """

    def setUp(self):
        Fixture.setUp(self)
        config.push('demo-fixture', '''
[launchpad]
is_demo: true
site_message = This is a demo site mmk. \
<a href="http://example.com">File a bug</a>.
            ''')
        self.addCleanup(lambda: config.pop('demo-fixture'))


class DisableTriggerFixture(Fixture):
    """Let tests disable database triggers."""

    def __init__(self, table_triggers=None):
        self.table_triggers = table_triggers or {}

    def setUp(self):
        super(DisableTriggerFixture, self).setUp()
        self._disable_triggers()
        self.addCleanup(self._enable_triggers)

    def _process_triggers(self, mode):
        with dbuser('postgres'):
            for table, trigger in self.table_triggers.items():
                sql = ("ALTER TABLE %(table)s %(mode)s trigger "
                       "%(trigger)s") % {
                    'table': table,
                    'mode': mode,
                    'trigger': trigger}
                IStore(LibraryFileAlias).execute(sql)

    def _disable_triggers(self):
        self._process_triggers(mode='DISABLE')

    def _enable_triggers(self):
        self._process_triggers(mode='ENABLE')
