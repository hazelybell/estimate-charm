# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""XML-RPC interface for extracting real time stats from the appserver."""

__metaclass__ = type
__all__ = ["OpStats"]

from cStringIO import StringIO
from time import time

from lp.services.webapp import LaunchpadXMLRPCView


class OpStats(LaunchpadXMLRPCView):
    """The XML-RPC API for extracting operational statistics."""

    # Statistics maintained by the publication machinery. Class global.
    stats = {} # Initialized by OpStats.resetStats()

    @classmethod
    def resetStats(cls):
        """Reset the collected stats to 0."""
        OpStats.stats.update({
            # Global
            'requests': 0, # Requests, all protocols, all statuses
            'retries': 0, # Optimistic transaction retries.
            'soft timeouts': 0, # Requests that generated a soft timeout OOPS
            'timeouts': 0, # Requests that generated a hard timeout OOPS

            # XML-RPC specific
            'xml-rpc requests': 0, # XML-RPC requests, all statuses
            'xml-rpc faults': 0, # XML-RPC requests returning a Fault

            # HTTP specific
            'http requests': 0,
            '404s': 0, # Not Found
            '500s': 0, # Internal Server Error (eg. unhandled exception)
            '503s': 0, # Service Unavailable (eg. Timeout)
            '1XXs': 0, # Informational (Don't think Launchpad produces these)
            '2XXs': 0, # Successful
            '3XXs': 0, # Redirection
            '4XXs': 0, # Client Errors
            '5XXs': 0, # Server Errors
            '6XXs': 0, # Internal Errors
            '5XXs_b': 0, # Server Errors returned to browsers (not robots).
            })

    def opstats(self):
        """Return a dictionary of a number of operational statistics.

        Keys currently are:
            requests -- # requests served by this appserver.
            xml-rpc requests -- # xml-rpc requests served.
            404s   -- 404 status responses served (Not Found)
            500s   -- 500 status responses served (Unhandled exceptions)
            503s   -- 503 status responses served (Timeouts)
            3XXs   -- 300-399 status responses served (Redirection)
            4XXs   -- 400-499 status responses served (Client Errors)
            5XXs   -- 500-599 status responses served (Server Errors)
            6XXs   -- 600-600 status responses served (Internal Errors)
            5XXs_b -- As 5XXs, but returned to browsers (not robots).
        """
        return OpStats.stats

    def __call__(self):
        now = time()
        out = StringIO()
        for stat_key in sorted(OpStats.stats.keys()):
            print >> out, '%s:%d@%d' % (
                    # Make keys more cricket friendly
                    stat_key.replace(' ', '_').replace('-', ''),
                    OpStats.stats[stat_key], now
                    )
        self.request.response.setHeader(
                'Content-Type', 'text/plain; charset=US-ASCII'
                )
        return out.getvalue()


OpStats.resetStats() # Initialize the statistics

