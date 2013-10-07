/* Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.code.branch.mergeproposal.test', function (Y) {
    var module = Y.lp.code.branchmergeproposal.diff;

    /*
     * A Mock client that always calls success on get.
     */
    var MockClient = function() {};
    MockClient.prototype = {
        'get': function(uri, config) {
            var content = Y.Node.create('<p>Sample diff.</p>');
            config.on.success(content);
        }
    };

    var tests = Y.namespace('lp.code.branch.mergeproposal.test');
    tests.suite = new Y.Test.Suite('code.branch.mergeproposal Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'Test branch diff functions',

        /*
         * Diff overlays should reopen with multiple clicks. The widget's
         * visible attribute must be toggled, too.
         */
        test_diff_overlay_multiple_opens: function() {
            // Setup mock client and initialize the link click handler.
            var mock_client = new MockClient();
            var link_node = Y.one('#test-diff-popup');
            var api_url = link_node.one('a.api-ref').getAttribute('href');
            module.link_popup_diff_onclick(link_node, mock_client);

            // Open the overlay once.
            link_node.one('a.diff-link').simulate('click');
            var widget = module.rendered_overlays[api_url];
            var overlay = widget.get('boundingBox');
            Y.Assert.isNotNull(overlay);
            Y.Assert.areEqual(overlay.getStyle('display'), 'block');
            Y.Assert.isTrue(widget.get('visible'));

            // verify that the widget has a header div
            Y.Assert.isNotNull(Y.one('.yui3-widget-hd'));

            // Close the overlay.
            overlay.one('.close a').simulate('click');
            Y.Assert.areEqual(overlay.getStyle('display'), 'none');
            Y.Assert.isFalse(widget.get('visible'));

            // Open it again.
            link_node.one('a.diff-link').simulate('click');
            Y.Assert.areEqual(overlay.getStyle('display'), 'block');
            Y.Assert.isTrue(widget.get('visible'));
        }

        }));


}, '0.1', {
    requires: ['test', 'lp.testing.helpers', 'test-console',
        'lp.code.branchmergeproposal.diff', 'node-event-simulate', 'lp.client']
});
