/**
 * Copyright 2012 Canonical Ltd. This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Tests for lp.soyuz.archive_packages.
 *
 * @module lp.soyuz.archive_packages
 * @submodule test
 */

YUI.add('lp.soyuz.archive_packages.test', function(Y) {

    var namespace = Y.namespace('lp.soyuz.archive_packages.test');

    var suite = new Y.Test.Suite("archive_packages Tests");
    var module = Y.lp.soyuz.archive_packages;

    var pending_job = Y.one('#pending-job-template').getContent();
    var pending_job_no_link = Y.one(
        '#pending-job-template-no-link').getContent();

    var TestPendingCopyJobWidgetNoLink = {
        name: "TestPendingCopyJobWidgetNoLink",

        setUp: function() {
            Y.one("#placeholder")
                .empty()
                .append(Y.Node.create(pending_job));
        },

        test_instanciation: function() {
            // The widget is instanciated even without a link to delete the
            // widget's html.
            var area = Y.one('.pending-job-no-link');
            this.widget = new module.PendingCopyJobWidget(
                {srcNode: area, archive_uri: '/archive/4'});
            this.widget.render();
        }

    };

    suite.add(new Y.Test.Case(TestPendingCopyJobWidgetNoLink));

    var TestPendingCopyJobWidget = {
        name: "TestPendingCopyJobWidget",

        setUp: function() {
            Y.one("#placeholder")
                .empty()
                .append(Y.Node.create(pending_job));
            var area = Y.one('.pending-job');
            this.widget = new module.PendingCopyJobWidget(
                {srcNode: area, archive_uri: '/archive/4'});
            this.widget.render();
        },

        simulate_cancel_click: function() {
            // Simulate a click on the cancel link.
            var link = Y.one("#placeholder").one('.remove-notification');
            link.simulate('click');
        },

        mock_lp_client: function() {
            // Mock lp client.
            this.mockio = new Y.lp.testing.mockio.MockIo();
            this.widget.client.io_provider = this.mockio;
        },

        test_job_id_parsed: function() {
            Y.Assert.areEqual('3', this.widget.get('job_id'));
        },

        test_cancel_fun_wired: function() {
            // Make sure that the cancel event is fired when the cancel button
            // is clicked.

            this.mock_lp_client();

            // Setup event listener.
            var event_fired = false;
            var handleEvent = function(e) {
                event_fired = true;
            };
            this.widget.on(
                this.widget.name + ":cancel",
                handleEvent, this.widget);

            this.simulate_cancel_click();

            Y.Assert.areSame(1, this.mockio.requests.length);
            Y.Assert.isTrue(event_fired);
        },

        test_cancel_success_cleans_html: function() {
            this.mock_lp_client();
            this.simulate_cancel_click();
            this.mockio.success({
                responseText:'.',
                responseHeaders: {'Content-Type': 'application/xhtml'}
            });
            // The HTML chunk has been deleted.
            Y.Assert.isNull(Y.one("#placeholder").one('.pending-job'));
        },

        test_show_spinner: function() {
            this.widget.showSpinner();
            Y.Assert.isNotNull(Y.one("#placeholder").one('.spinner'));
        },

        test_hide_spinner: function() {
            this.widget.showSpinner();
            this.widget.hideSpinner();
            Y.Assert.isNull(Y.one("#placeholder").one('.spinner'));
        }

    };

    suite.add(new Y.Test.Case(TestPendingCopyJobWidget));

    namespace.suite = suite;

}, "0.1", {"requires": [
               "lp.soyuz.archive_packages", "node", "lp.testing.mockio",
               "node-event-simulate", "test", "lp.anim"]});
