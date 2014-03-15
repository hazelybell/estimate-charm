/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Tests for lp.code.branchmergeproposal.updater.
 *
 */
YUI.add('lp.branchmergeproposal.updater.test', function (Y) {
var module = Y.lp.code.branchmergeproposal.updater;
var UpdaterWidget = module.UpdaterWidget;


var tests = Y.namespace('lp.branchmergeproposal.updater.test');
tests.suite = new Y.Test.Suite("BranchMergeProposal Updater Tests");

/*
 * Tests for when the updater is built on top of a pending diff.
 *
 */

var pending_mp = Y.one('#pending-mp').getContent();

tests.suite.add(new Y.Test.Case({

    name: 'branchmergeproposal-updater-pending-tests',

    setUp: function() {
        Y.one("#placeholder")
            .empty()
            .append(Y.Node.create(pending_mp));
        var diff_area = Y.one('#diff-area');
        var summary_node = Y.one('#proposal-summary');
        this.updater = new UpdaterWidget(
            {srcNode: diff_area, summary_node: summary_node});

        LP.cache.context = {
            web_link: "https://code.launchpad.dev/~foo/bar/foobr/+merge/123"};

    },

    tearDown: function() {
        this.updater.destroy();
    },

    test_default_values: function() {
        Y.Assert.isTrue(this.updater.get('pending'));
        Y.Assert.areEqual(
            '',
            this.updater.get('diff'));
    },

    test__setup_diff_container: function() {
        this.updater._setup_diff_container();
        Y.Assert.isFalse(this.updater.get('pending'));
        Y.Assert.areEqual(
            "Preview Diff ",
            this.updater.get(
                'srcNode').one('#review-diff h2').get('text'));
        Y.Assert.areEqual(
            "",
            this.updater.get(
                'srcNode').one('.diff-content').get('text'));
    },

    test__setup_diff_stats_container: function() {
        Y.Assert.isNull(this.updater.get('diff_stats'));
        this.updater._setup_diff_stats_container();
        Y.Assert.areEqual('', this.updater.get('diff_stats'));
    },

    test_set_diff_stats: function() {
        this.updater.set('diff_stats', '13 lines (+4/-0) 1 file modified');
        Y.Assert.areEqual(
            '13 lines (+4/-0) 1 file modified',
            this.updater.get('diff_stats'));
    },

    test_set_status_updating: function() {
        this.updater.set_status_updating();
        Y.Assert.areEqual(
            '/@@/spinner',
            Y.one('h2').one('img').getAttribute('src'));
    },

    test_set_status_longpolling: function() {
        this.updater.set_status_longpolling();
        Y.Assert.areEqual(
            '/@@/longpoll_loading',
            Y.one('h2').one('img').getAttribute('src'));
    },

    test_set_status_longpollerror: function() {
        this.updater.set_status_longpollerror();
        Y.Assert.areEqual(
            '/@@/longpoll_error',
            Y.one('h2').one('img').getAttribute('src'));
    },

    test_cleanup_status: function() {
        this.updater._setup_diff_container();
        this.updater.set_status_updating();
        this.updater.cleanup_status();
        Y.Assert.areEqual(
            'Preview Diff ',
            Y.one('h2').get('innerHTML'));
    },

    test_get_diff: function() {
        this.updater._setup_diff_container();
        Y.one('.diff-content').set(
            'innerHTML', 'this is a <span>diff</span>');
        Y.Assert.areEqual(
            'this is a <span>diff</span>',
            this.updater.get('diff'));
    },

    test_set_diff: function() {
        this.updater.set('diff', 'this is a <span>diff</span>');
        Y.Assert.areEqual(
            'this is a <span>diff</span>',
            Y.one('.diff-content').get('innerHTML'));
    },

    test_update_diff_success: function() {
        var mockio = new Y.lp.testing.mockio.MockIo();
        this.updater.get('lp_client').io_provider = mockio;
        Y.Assert.areEqual(
            '',
            this.updater.get('diff'));
        this.updater.update_diff();
        mockio.success({
            responseText: 'New <span>diff</span>',
            responseHeaders: {'Content-Type': 'text/html'}});

        Y.Assert.areEqual(
            'New <span>diff</span>',
            this.updater.get('diff'));
    },

    test_update_stats_success: function() {
        var mockio = new Y.lp.testing.mockio.MockIo();
        this.updater.get('lp_client').io_provider = mockio;
        Y.Assert.isNull(this.updater.get('diff_stats'));
        this.updater.update_stats();
        mockio.success({
            responseText: '13 lines (+4/-0) 1 file modified',
            responseHeaders: {'Content-Type': 'text/html'}});

        Y.Assert.areEqual(
            '13 lines (+4/-0) 1 file modified',
            this.updater.get('diff_stats'));
    },

    test_update_diff_fires_event: function() {
        var fired = false;
        var mockio = new Y.lp.testing.mockio.MockIo();
        this.updater.get('lp_client').io_provider = mockio;
        this.updater.on(this.updater.NAME + '.updated', function() {
            fired = true;
        });
        this.updater.update_diff();
        mockio.success({
            responseText: 'New <span>diff</span>',
            responseHeaders: {'Content-Type': 'text/html'}});

        Y.Assert.isTrue(fired);
    }

}));

/*
 * Tests for when the updater is built on top of an existing diff.
 *
 */
var current_mp = Y.one('#current-mp').getContent();

tests.suite.add(new Y.Test.Case({

    name: 'branchmergeproposal-updater-refresh-tests',

    setUp: function() {
        Y.one("#placeholder")
            .empty()
            .append(Y.Node.create(current_mp));
        var diff_area = Y.one('#diff-area');
        this.updater = new UpdaterWidget({srcNode: diff_area});
    },

    tearDown: function() {
        this.updater.destroy();
    },

    test_default_values: function() {
        Y.Assert.isFalse(this.updater.get('pending'));
        Y.Assert.areEqual(
            'Example diff',
            this.updater.get('diff'));
    },

    test_get_diff: function() {
        Y.one('.diff-content').set(
            'innerHTML', 'this is a <span>diff</span>');
        Y.Assert.areEqual(
            'this is a <span>diff</span>',
            this.updater.get('diff'));
    }

}));

tests.suite.add(new Y.Test.Case({

    name: 'branchmergeproposal-updater-utilities',

    test_is_mp_diff_updated_modified: function() {
        var data = {what: 'modified', edited_fields: ['preview_diff']};
        Y.Assert.isTrue(module.is_mp_diff_updated(data));
    },

    test_is_mp_diff_updater_deleted: function() {
        var data = {what: 'deleted'};
        Y.Assert.isFalse(module.is_mp_diff_updated(data));
    },

    test_is_mp_diff_updated_title_changed: function() {
        var data = {what: 'modified', edited_fields: ['title']};
        Y.Assert.isFalse(module.is_mp_diff_updated(data));
    }

}));


}, '0.1', {
    requires: ['lp.testing.runner', 'test', 'dump', 'test-console', 'node',
               'lp.testing.mockio', 'event',
               'lp.code.branchmergeproposal.updater']
});
