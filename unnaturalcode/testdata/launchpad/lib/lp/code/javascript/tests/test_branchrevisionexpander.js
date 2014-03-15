/* Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.code.branch.revisionexpander.test', function (Y) {
    var module = Y.lp.code.branch.revisionexpander;

    var MockClient = function() {};
    MockClient.prototype = {
        'calls': [],
        'get': function(uri, config) {
            this.calls.push({'uri': uri});
            config.on.success(samplediff);
        }
    };

    var samplediff = (
        "=== modified file 'README'\n" +
        "--- README 2011-01-20 23:05:06 +0000\n" +
        "+++ README 2011-06-30 10:47:28 +0000\n" +
        "@@ -1,3 +1,4 @@\n" +
        "+Green sheep!\n" +
        " =========\n" +
        " testtools\n" +
        " =========\n" +
        "            \n");


    var tests = Y.namespace('lp.code.branch.revisionexpander.test');
    tests.suite = new Y.Test.Suite('code.branch.revisionexpander Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'Test difftext_to_node',

        /*
         * Unified diffs are rendered to a table, one row per line
         */
        test_difftext_to_node_outputs_table: function() {
            var node = module.difftext_to_node(samplediff);
            Y.Assert.areEqual('TABLE', node.get('tagName'));
            Y.Assert.isTrue(node.hasClass('diff'));
            /* samplediff has 9 lines, so the table will have 9 rows
             * (trailing newlines don't result in a final row containing an
             * empty string) */
            Y.Assert.areEqual(9, node.get('children').size());
        },

        /*
         * Diffs are not interpreted as HTML.
         */
        test_difftext_to_node_escaping: function() {
            var node = module.difftext_to_node("<p>hello</p>");
            var td = node.one('td');
            Y.Assert.isNull(td.one('p'));
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'Tests for bmp_diff_loader and bmp_get_diff_url',

        setUp: function() {
            LP.cache.branch_diff_link = 'fake-link-base/';
            },

        tearDown: function() {
            delete LP.cache.branch_diff_link;
            },

        /*
         * bmp_diff_loader fetches from the URI specified by the div id and
         * renders a diff.
         */
        test_bmp_diff_loader_fetches_from_diff_uri: function() {
            var FakeExpander = function() {};
            FakeExpander.prototype = {
                'icon_node':
                    Y.Node.create('<div id="expandable-23-45"></div>'),
                'receive': function (node) {
                    this.received_node = node;
                }
            };
            var mock_client = new MockClient();
            var fake_expander = new FakeExpander();
            module.bmp_diff_loader(fake_expander, mock_client);
            Y.Assert.areEqual(
                'fake-link-base/45/22', mock_client.calls[0].uri);
            Y.Assert.areEqual(
                'TABLE', fake_expander.received_node.get('tagName'));
            },

        /*
         * bmp_get_diff_url(revno) gets the URL for a diff of just that revision
         */
        test_bmp_get_diff_url_one_arg: function() {
            Y.Assert.areEqual(
                'fake-link-base/1234',
                module.bmp_get_diff_url(1234));
            },

        /*
         * bmp_get_diff_url(start_revno, end_revno) gets the URL for a diff of
         * the given revision range.
         */
        test_bmp_get_diff_url_two_args: function() {
            Y.Assert.areEqual(
                'fake-link-base/33/22',
                module.bmp_get_diff_url(22, 33));
            },

        /*
         * bmp_get_diff_url(0, 1) just returns URL_BASE/1, rather than
         * URL_BASE/1/0 which Loggerhead will reject.
         */
        test_bmp_get_diff_url_of_0_to_1: function() {
            Y.Assert.areEqual(
                'fake-link-base/1',
                module.bmp_get_diff_url(0, 1));
            },

        /*
         * bmp_get_diff_url(0, 2) just returns URL_BASE/1, rather than
         * URL_BASE/1/0 which Loggerhead will reject.
         */
        test_bmp_get_diff_url_of_0_to_2: function() {
            Y.Assert.areEqual(
                'fake-link-base/2/null:',
                module.bmp_get_diff_url(0, 2));
            }
    }));


}, '0.1', {
    requires: ['test', 'lp.testing.helpers', 'test-console',
        'lp.code.branch.revisionexpander', 'lp.client', 'node-event-simulate']
});
