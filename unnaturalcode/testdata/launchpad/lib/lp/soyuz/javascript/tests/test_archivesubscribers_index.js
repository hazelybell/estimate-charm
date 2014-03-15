/* Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.soyuz.archivesubscribers_index.test', function (Y) {
    var Assert = Y.Assert;  // For easy access to isTrue(), etc.
    var tests = Y.namespace('lp.soyuz.archivesubscribers_index.test');
    tests.suite = new Y.Test.Suite('soyuz.archivesubscribers_index Tests');

    tests.suite.add(new Y.Test.Case({

        name: 'add-subscriber',

        setUp: function() {
            this.add_subscriber_placeholder = Y.one(
                '#add-subscriber-placeholder');
            this.archive_subscribers_table_body = Y.one(
                '#archive-subscribers').one('tbody');
            this.error_div = Y.one('#errors');
            this.subscribers_div = Y.one('#subscribers');


            // Ensure there are no errors displayed.
            this.error_div.set('innerHTML', '');

            // Ensure the add subscriber place-holder is empty.
            this.add_subscriber_placeholder.set('innerHTML', '');

            // Ensure the table has the correct structure.
            this.archive_subscribers_table_body.set(
                'innerHTML', [
                    '<tr class="add-subscriber">',
                    '<td>New 1</td>',
                    '<td>New 2</td>',
                    '<td>New 3</td>',
                    '<td>Add</td>',
                    '</tr>',
                    '<tr>',
                    '<td>Existing 1</td>',
                    '<td>Existing 2</td>',
                    '<td>Existing 3</td>',
                    '<td>Edit</td>',
                    '</tr>'
                    ].join(''));

            this.add_subscriber_row = Y.one(
                '#archive-subscribers .add-subscriber');
        },

        test_add_row_displayed_by_default: function() {
            // The add subscriber row is displayed when the JS is not run.
            Assert.areEqual(
                'table-row', this.add_subscriber_row.getStyle('display'),
                'The add subscriber row should display when the js is not run.');
        },

        test_subscribers_displayed_by_default: function() {
            // The subscribers section is displayed when the js is not run.
            Assert.areEqual(
                'block', this.subscribers_div.getStyle('display'),
                'The subscribers section should display without js.');
        },

        test_add_row_hidden_after_setup: function() {
            // The add subscriber row is hidden during setup.
            Y.lp.soyuz.archivesubscribers_index.setup_archivesubscribers_index();
            Assert.areEqual(
                'none', this.add_subscriber_row.getStyle('display'),
                'The add subscriber row should be hidden during setup.');
        },

        test_subscribers_section_displayed_after_setup: function() {
            // The subscribers div normally remains displayed after setup.
            Y.lp.soyuz.archivesubscribers_index.setup_archivesubscribers_index();
            Assert.areEqual(
                'block', this.subscribers_div.getStyle('display'),
                'The subscribers div should remain displayed after setup.');
        },

        test_subscribers_section_hidden_when_no_subscribers: function() {
            // The subscribers div is hidden when there are no subscribers.

            // Add a paragraph with the no-subscribers id.
            this.error_div.set('innerHTML', '<p id="no-subscribers">blah</p>');
            Y.lp.soyuz.archivesubscribers_index.setup_archivesubscribers_index();
            Assert.areEqual(
                'none', this.subscribers_div.getStyle('display'),
                'The subscribers div should be hidden when there are ' +
                'no subscribers.');
        },

        test_add_row_displayed_when_errors_present: function() {
            // The add subscriber row is not hidden if there are validation
            // errors.

            // Add an error paragraph.
            this.error_div.set('innerHTML', '<p class="error message">Blah</p>');
            Y.lp.soyuz.archivesubscribers_index.setup_archivesubscribers_index();
            Assert.areEqual(
                'table-row', this.add_subscriber_row.getStyle('display'),
                'The add subscriber row should not be hidden if there are ' +
                'errors present.');
        },

        test_add_access_link_added_after_setup: function() {
            // The 'Add access' link is created during setup.

            Y.lp.soyuz.archivesubscribers_index.setup_archivesubscribers_index();
            Assert.areEqual(
                '<a class="js-action sprite add" href="#">Add access</a>',
                this.add_subscriber_placeholder.get('innerHTML'),
                "The 'Add access' link should be created during setup.");
        },

        test_click_add_access_displays_add_row: function() {
            // The add subscriber row is displayed after clicking 'Add access'.
            Y.lp.soyuz.archivesubscribers_index.setup_archivesubscribers_index();
            var link_node = this.add_subscriber_placeholder.one('a');
            Assert.areEqual(
                'Add access', link_node.get('innerHTML'));

            Y.Event.simulate(Y.Node.getDOMNode(link_node), 'click');

            Assert.areEqual(
                'table-row', this.add_subscriber_row.getStyle('display'),
                "The add subscriber row should be displayed after clicking " +
                "'Add access'");
        }
    }));
}, '0.1', {
    requires: ['test', 'lp.testing.helpers', 'test-console',
        'lp.soyuz.archivesubscribers_index']
});
