YUI.add('lp.bugtask_index.test', function (Y) {

var tests = Y.namespace('lp.bugtask_index.test');
tests.suite = new Y.Test.Suite("Bugtask deletion Tests");
var module = Y.lp.bugs.bugtask_index;

tests.suite.add(new Y.Test.Case({
    name: 'Bugtask delete',

        setUp: function() {
            module.ANIM_DURATION = 0;
            this.link_conf = {
                id: '49',
                row_id: 'tasksummary49',
                form_row_id: 'tasksummary49',
                user_can_delete: true,
                targetname: 'bugtarget'
            };
            this.no_form_link_conf = {
                id: '50',
                row_id: 'tasksummary50',
                user_can_delete: true
            };
            window.LP = {
                links: {me : "/~user"},
                cache: {
                    bugtask_data: {
                        49: this.link_conf,
                        50: this.no_form_link_conf
                    }
                }
            };
            this.fixture = Y.one('#fixture');
            var bugtasks_table = Y.Node.create(
                    Y.one('#form-template').getContent());
            this.fixture.appendChild(bugtasks_table);
            this.delete_link = bugtasks_table.one('#bugtask-delete-task49');
            this.no_form_delete_link =
                bugtasks_table.one('#bugtask-delete-task50');
        },

        tearDown: function() {
            if (this.fixture !== null) {
                this.fixture.empty();
            }
            Y.one('#request-notifications').empty();
            delete this.fixture;
            delete window.LP;
        },

        test_show_spinner: function() {
            // Test the delete progress spinner is shown.
            module._showDeleteSpinner(this.delete_link);
            Y.Assert.isNotNull(this.fixture.one('.spinner'));
            Y.Assert.isTrue(this.delete_link.hasClass('hidden'));
        },

        test_hide_spinner_restore_delete_link: function() {
            // Test the delete progress spinner is hidden and delete link is
            // visible again.
            module._showDeleteSpinner(this.delete_link);
            module._hideDeleteSpinner(this.delete_link, true);
            Y.Assert.isNull(this.fixture.one('.spinner'));
            Y.Assert.isFalse(this.delete_link.hasClass('hidden'));
        },

        test_hide_spinner_delete_link_stays_hidden: function() {
            // Test the delete progress spinner is hidden and delete link
            // remains hidden.
            module._showDeleteSpinner(this.delete_link);
            module._hideDeleteSpinner(this.delete_link, false);
            Y.Assert.isNull(this.fixture.one('.spinner'));
            Y.Assert.isTrue(this.delete_link.hasClass('hidden'));
        },

        _test_delete_confirmation: function(click_ok) {
            // Test the delete confirmation dialog when delete is clicked.
            var orig_delete_bugtask = module.delete_bugtask;

            var delete_called = false;
            var self = this;
            module.delete_bugtask = function(delete_link, conf) {
                Y.Assert.areEqual(self.delete_link, delete_link);
                Y.Assert.areEqual(self.link_conf, conf);
                delete_called = true;
            };
            module.setup_bugtask_table();
            this.delete_link.simulate('click');
            var co = Y.one('.yui3-overlay.yui3-lp-app-confirmationoverlay');
            var actions = co.one('.yui3-lazr-formoverlay-actions');
            var btn_style;
            if (click_ok) {
                btn_style = '.ok-btn';
            } else {
                btn_style = '.cancel-btn';
            }
            var button = actions.one(btn_style);
            button.simulate('click');
            Y.Assert.areEqual(click_ok, delete_called);
            Y.Assert.isTrue(
                    co.hasClass('yui3-lp-app-confirmationoverlay-hidden'));
            module.delete_bugtask = orig_delete_bugtask;
        },

        test_delete_confirmation_ok: function() {
            // Test the delete confirmation dialog Ok functionality.
            this._test_delete_confirmation(true);
        },

        test_delete_confirmation_cancel: function() {
            // Test the delete confirmation dialog Cancel functionality.
            this._test_delete_confirmation(false);
        },

        test_setup_bugtask_table: function() {
            // Test that the bugtask table is wired up, the pickers and the
            // delete links etc.
            var connect_picker_called = false;
            var orig_reconnectPicker = Y.lp.app.picker.reconnectPicker;
            Y.lp.app.picker.reconnectPicker = function(show_widget_id) {
                connect_picker_called = show_widget_id ===
                    'show-widget-product';
            };
            var orig_confirm_bugtask_delete = module._confirm_bugtask_delete;
            var self = this;
            var confirm_delete_called = false;
            var expected_delete_link = self.delete_link;
            var expected_link_conf = self.link_conf;
            module._confirm_bugtask_delete = function(delete_link, conf) {
                Y.Assert.areEqual(expected_delete_link, delete_link);
                Y.Assert.areEqual(expected_link_conf, conf);
                confirm_delete_called = true;
            };
            module.setup_bugtask_table();

            // Test wiring of delete link for row with an associated form.
            this.delete_link.simulate('click');
            this.wait(function() {
                // Wait for the events to fire.
                Y.Assert.isTrue(connect_picker_called);
                Y.Assert.isTrue(confirm_delete_called);
            }, 20);

            // Test wiring of delete link for row without an associated form.
            confirm_delete_called = false;
            connect_picker_called = false;
            expected_delete_link = self.no_form_delete_link;
            expected_link_conf = self.no_form_link_conf;
            this.no_form_delete_link.simulate('click');
            Y.Assert.isFalse(connect_picker_called);
            Y.Assert.isTrue(confirm_delete_called);

            Y.lp.app.picker.reconnectPicker = orig_reconnectPicker;
            module._confirm_bugtask_delete = orig_confirm_bugtask_delete;
        },

        test_render_bugtask_table: function() {
            // Test that a new bug task table is rendered and setup.
            var orig_setup_bugtask_table = module.setup_bugtask_table;
            var setup_called = false;
            module.setup_bugtask_table = function() {
                setup_called = true;
            };
            var test_table =
                '<table id="affected-software">'+
                '<tr><td>foo</td></tr></table>';
            module._render_bugtask_table(test_table);
            Y.Assert.isTrue(setup_called);
            Y.Assert.areEqual(
                '<tbody><tr><td>foo</td></tr></tbody>',
                this.fixture.one('table#affected-software').getContent());
            module.setup_bugtask_table = orig_setup_bugtask_table;
        },

        test_process_bugtask_delete_redirect_response: function() {
            // Test the processing of a XHR delete result which is to
            // redirect the browser to a new URL.
            var orig_redirect = module._redirect;
            var redirect_called = false;
            module._redirect = function(url) {
                Y.Assert.areEqual('http://foo', url);
                redirect_called = true;
            };
            var response = new Y.lp.testing.mockio.MockHttpResponse({
                responseText: '{"bugtask_url": "http://foo"}',
                responseHeaders: {'Content-type': 'application/json'}});
            module._process_bugtask_delete_response(
                response, this.link_conf.id, this.link_conf.row_id,
                this.delete_link);
            this.wait(function() {
                // Wait for the animation to complete.
                Y.Assert.isTrue(redirect_called);
            }, 50);
            module._redirect = orig_redirect;
        },

        test_process_bugtask_delete_not_found_response: function() {
            // Test the processing of a XHR delete request which is for a
            // bugtask which has already been deleted displays an
            // informational message and deletes the affected bugtask row.

            var orig_render_bugtask_table = module._render_bugtask_table;
            var render_table_called = false;
            module._render_bugtask_table = function(new_table) {
                render_table_called = true;
            };
            var orig_redirect = module._redirect;
            var redirect_called = false;
            module._redirect = function(url) {
                redirect_called = true;
            };
            var response = new Y.lp.testing.mockio.MockHttpResponse({
                responseText: '<html></html>',
                status: 404,
                responseHeaders: {
                    'Content-type': 'text/html'}});
            Y.Assert.isNotNull(Y.one('#' + this.link_conf.row_id));
            module._process_bugtask_delete_response(
                response, this.link_conf.id, this.link_conf.row_id,
                this.delete_link);
            this.wait(function() {
                // Wait for the animation to complete.
                var node = Y.one('div#request-notifications ' +
                                    'div.informational.message');
                Y.Assert.isFalse(render_table_called);
                Y.Assert.isFalse(redirect_called);
                Y.Assert.areEqual(
                    'Bug task affecting bugtarget has already been deleted.',
                    node.getContent());
                Y.Assert.isNull(Y.one('#' + this.link_conf.row_id));
                Y.Assert.isUndefined(
                    LP.cache.bugtask_data[this.link_conf.id]);
            }, 50);
            module._render_bugtask_table = orig_render_bugtask_table;
            module._redirect = orig_redirect;
        },

        test_process_bugtask_delete_error_response: function() {
            // Test the processing of a XHR delete request which results in
            // an error message to be displayed.
            var orig_redirect = module._redirect;
            var redirect_called = false;
            module._redirect = function(url) {
                redirect_called = true;
            };
            this.delete_link.addClass('hidden');
            var notifications = '[ [40, "Delete Error"] ]';
            var response = new Y.lp.testing.mockio.MockHttpResponse({
                responseText: 'null',
                responseHeaders: {
                    'Content-type': 'application/json',
                    'X-Lazr-Notifications': notifications}});
            module._process_bugtask_delete_response(
                response, this.link_conf.id, this.link_conf.row_id,
                this.delete_link);
            this.wait(function() {
                // Wait for the animation to complete.
                Y.Assert.isFalse(redirect_called);
                var node = Y.one('div#request-notifications ' +
                                    'div.error.message');
                Y.Assert.areEqual('Delete Error', node.getContent());
                Y.Assert.isTrue(this.delete_link.hasClass('hidden'));
            }, 50);
            module._redirect = orig_redirect;
        },

        test_process_bugtask_delete_new_table_response: function() {
            // Test the processing of a XHR delete result which is to
            // replace the current bugtasks table.
            var orig_render_bugtask_table = module._render_bugtask_table;
            var render_table_called = false;
            module._render_bugtask_table = function(new_table) {
                Y.Assert.areEqual('<table>Foo</table>', new_table);
                render_table_called = true;
            };
            var notifications = '[ [20, "Delete Success"] ]';
            var response = new Y.lp.testing.mockio.MockHttpResponse({
                responseText: '<table>Foo</table>',
                responseHeaders: {
                    'Content-type': 'text/html',
                    'X-Lazr-Notifications': notifications}});
            module._process_bugtask_delete_response(
                response, this.link_conf.id, this.link_conf.row_id,
                this.delete_link);
            this.wait(function() {
                // Wait for the animation to complete.
                Y.Assert.isTrue(render_table_called);
                var node = Y.one('div#request-notifications ' +
                                    'div.informational.message');
                Y.Assert.areEqual('Delete Success', node.getContent());
                Y.Assert.isUndefined(
                    LP.cache.bugtask_data[this.link_conf.id]);
            }, 50);
            module._render_bugtask_table = orig_render_bugtask_table;
        },

        test_delete_bugtask: function() {
            // Test that when delete_bugtask is called, the expected XHR call
            // is made.
            var orig_delete_repsonse =
                module._process_bugtask_delete_response;

            var delete_response_called = false;
            var self = this;
            module._process_bugtask_delete_response =
                    function(response, bugtask_id, row_id, delete_link) {
                Y.Assert.areEqual('<p>Foo</p>', response.responseText);
                Y.Assert.areEqual(self.link_conf.id, bugtask_id);
                Y.Assert.areEqual(self.link_conf.row_id, row_id);
                Y.Assert.areEqual(self.delete_link, delete_link);
                delete_response_called = true;
            };

            var mockio = new Y.lp.testing.mockio.MockIo();
            var conf = Y.merge(this.link_conf, {io_provider: mockio});
            module.delete_bugtask(this.delete_link, conf);
            mockio.success({
                responseText: '<p>Foo</p>',
                responseHeaders: {'Content-Type': 'text/html'}});
            // Check the parameters passed to the io call.
            Y.Assert.areEqual(
                this.delete_link.get('href'),
                mockio.last_request.url);
            Y.Assert.areEqual(
                'POST', mockio.last_request.config.method);
            Y.Assert.areEqual(
                'application/json; application/xhtml',
                mockio.last_request.config.headers.Accept);
            Y.Assert.areEqual(
                'field.actions.delete_bugtask=Delete',
                mockio.last_request.config.data);
            Y.Assert.isTrue(delete_response_called);

            module._process_bugtask_delete_response = orig_delete_repsonse;
        },

        test_delete_non_existent_bugtask: function() {
            // Test that when delete_bugtask is called and a 404 error occurs,
            // no error processing occurs (since it's not an error as such)
            // and the correct call is made to process the result.

            var orig_display_error = Y.lp.app.errors.display_error;
            var display_error_called = false;
            Y.lp.app.errors.display_error = function(flash_node, msg) {
                display_error_called = true;
            };
            var orig_delete_repsonse =
                module._process_bugtask_delete_response;

            var delete_response_called = false;
            var self = this;
            module._process_bugtask_delete_response =
                    function(response, bugtask_id, row_id, delete_link) {
                Y.Assert.areEqual(response.status, 404);
                Y.Assert.areEqual(self.link_conf.id, bugtask_id);
                Y.Assert.areEqual(self.link_conf.row_id, row_id);
                Y.Assert.areEqual(self.delete_link, delete_link);
                delete_response_called = true;
            };

            var mockio = new Y.lp.testing.mockio.MockIo();
            var conf = Y.merge(this.link_conf, {io_provider: mockio});
            module.delete_bugtask(this.delete_link, conf);
            mockio.failure({
                responseText: '<html></html>',
                status: 404,
                responseHeaders: {'Content-Type': 'text/html'}});
            Y.Assert.isTrue(delete_response_called);
            Y.Assert.isFalse(display_error_called);

            module._process_bugtask_delete_response = orig_delete_repsonse;
            Y.lp.app.errors.display_error = orig_display_error;
        }
}));

}, '0.1', {
    requires: ['lp.testing.runner', 'lp.testing.mockio', 'base', 'test',
               'test-console', 'node', 'node-event-simulate',
               'lp.bugs.bugtask_index', 'lp.app.picker', 'lp.mustache']
});
