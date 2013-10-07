/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.app.information_type.test', function (Y) {

    var tests = Y.namespace('lp.app.information_type.test');
    var ns = Y.lp.app.information_type;
    tests.suite = new Y.Test.Suite('lp.app.information_type Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'lp.app.information_type_tests',

        _should: {
            error: {
                test_change_event_empty: true
            }
        },

        setUp: function() {
            window.LP = {
                cache: {
                    context: {
                        web_link: ''
                    },
                    notifications_text: {
                        muted: ''
                    },
                    bug: {
                        information_type: 'Public',
                        self_link: '/bug/1'
                    },
                    information_type_data: {
                        PUBLIC: {
                            value: 'PUBLIC', name: 'Public',
                            is_private: false, order: 1,
                            description: 'Public Description'
                        },
                        PUBLICSECURITY: {
                            value: 'PUBLICSECURITY', name: 'Public Security',
                            is_private: false, order: 2,
                            description: 'Public Security Description'
                        },
                        PROPRIETARY: {
                            value: 'PROPRIETARY', name: 'Proprietary',
                            is_private: true, order: 3,
                            description: 'Proprietary Description'
                        },
                        USERDATA: {
                            value: 'USERDATA', name: 'Private',
                            is_private: true, order: 4,
                            description: 'Private Description'
                        }
                    }
                }
            };
            this.fixture = Y.one('#fixture');
            var portlet = Y.Node.create(
                    Y.one('#portlet-template').getContent());
            this.fixture.appendChild(portlet);
            this.mockio = new Y.lp.testing.mockio.MockIo();
            this.lp_client = new Y.lp.client.Launchpad({
                io_provider: this.mockio
            });

            Y.lp.bugs.subscribers.createBugSubscribersLoader({
                container_box: '#other-bug-subscribers',
                subscribers_details_view:
                    '/+bug-portlet-subscribers-details'});

        },

        tearDown: function () {
            if (this.fixture !== null) {
                this.fixture.empty(true);
            }
            delete this.fixture;
            delete this.mockio;
            delete this.lp_client;
            delete window.LP;
        },

        makeWidget: function() {
            var privacy_link = Y.one('#privacy-link');
            this.widget = ns.setup_choice(
                privacy_link, this.lp_client, LP.cache.bug, null, true);
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.app.information_type,
                "Cannot locate the lp.app.information_type module");
        },

        // The save XHR call works as expected.
        test_save: function() {
            this.makeWidget();
            var orig_save_success = ns.save_success;
            var save_success_called = false;
            ns.save_success = function(widget, context, value,
                                                   subscribers_list,
                                                   result_data) {
                Y.Assert.areEqual('USERDATA', value);
                Y.Assert.areEqual(
                    'subscribers', result_data.subscription_data);
                Y.Assert.areEqual(
                    'value', result_data.cache_data.item);
                Y.Assert.isBoolean(result_data.can_add_project_task);
                Y.Assert.isBoolean(result_data.can_add_package_task);
                save_success_called = true;
            };
            ns.save(
                    this.widget, 'PUBLIC', 'USERDATA', this.lp_client,
                    LP.cache.bug, null, true);
            this.mockio.success({
                responseText: '{"subscription_data": "subscribers",' +
                    '"cache_data": {"item": "value"},' +
                    '"can_add_project_task": true,' +
                    '"can_add_package_task": true}',
                responseHeaders: {'Content-Type': 'application/json'}});
            Y.Assert.areEqual(
                document.URL + '/+secrecy', this.mockio.last_request.url);
            Y.Assert.areEqual(
                'field.actions.change=Change&' +
                'field.information_type=USERDATA&' +
                'field.validate_change=on',
                this.mockio.last_request.config.data);
            Y.Assert.isTrue(save_success_called);
            ns.save_success = orig_save_success;
        },

        // A successful save updates the subscribers portlet.
        test_save_success_with_subscribers_data: function() {
            this.makeWidget();
            var flag = false;
            Y.on('test:banner:hide', function() {
                flag = true;
            });
            var summary = Y.one('#information-type-summary');
            summary.replaceClass('public', 'private');

            var load_subscribers_called = false;
            var subscribers_list = {
                _loadSubscribersFromList: function(subscription_data) {
                    Y.Assert.areEqual('subscriber', subscription_data);
                    load_subscribers_called = true;
                }
            };
            var result_data = {
                subscription_data: 'subscriber',
                cache_data: {
                    item1: 'value1',
                    item2: 'value2'
                }
            };
            ns.save_success(
                this.widget, LP.cache.bug, 'PUBLIC', subscribers_list,
                result_data);
            Y.Assert.isTrue(load_subscribers_called);
            Y.Assert.areEqual('value1', window.LP.cache.item1);
            Y.Assert.areEqual('value2', window.LP.cache.item2);
        },

        // A successful save updates the task actions.
        test_save_success_with_task_data: function() {
            this.makeWidget();
            var subscribers_list = {
                _loadSubscribersFromList: function(subscription_data) {
                }
            };
            var result_data = {
                can_add_project_task: false,
                can_add_package_task: true
            };
            ns.save_success(
                this.widget, LP.cache.bug, 'PUBLIC', subscribers_list,
                result_data);
            Y.Assert.isTrue(
                Y.one('#also-affects-product').hasClass('private-disallow'));
            Y.Assert.isFalse(
                Y.one('#also-affects-package').hasClass('private-disallow'));
        },

        // Select a new information type and respond with a validation error.
        _assert_save_with_validation_error: function() {
            this.makeWidget();
            var privacy_link = Y.one('#privacy-link');
            privacy_link.simulate('click');
            var private_choice = Y.one(
                '.yui3-ichoicelist-content a[href="#USERDATA"]');
            private_choice.simulate('click');
            // Check the save and respond with a status of 400.
            Y.Assert.areEqual(
                document.URL + '/+secrecy', this.mockio.last_request.url);
            Y.Assert.areEqual(
                'field.actions.change=Change&' +
                'field.information_type=USERDATA&' +
                'field.validate_change=on',
                this.mockio.last_request.config.data);
            this.mockio.respond({
                status: 400,
                statusText: 'Bug Visibility'});
        },

        // Selecting a new private information type shows the
        // confirmation dialog and calls save correctly when user says 'yes'.
        test_perform_update_information_type_to_private: function() {
            this._assert_save_with_validation_error();
            this.makeWidget();
            // The confirmation popup should be shown so stub out the save
            // method and check the behaviour.
            var orig_save = ns.save;
            var function_called = false;
            ns.save =
                    function(widget, initial_value, value, lp_client,
                             context, subscribers_list, validate_change) {
                // We only care if the function is called with
                // validate_change = false
                Y.Assert.areEqual('PUBLIC', initial_value);
                Y.Assert.areEqual('USERDATA', value);
                Y.Assert.isFalse(validate_change);
                function_called = true;
            };
            // We click 'yes' on the confirmation dialog.
            var co = Y.one('.yui3-overlay.yui3-lp-app-confirmationoverlay');
            var div = co.one('.yui3-lazr-formoverlay-actions');
            var ok = div.one('.ok-btn');
            ok.simulate('click');
            var description_node = Y.one('#information-type-description');
            Y.Assert.areEqual(
                    'Private Description', description_node.get('text'));
            var summary = Y.one('#information-type-summary');
            Y.Assert.isTrue(summary.hasClass('private'));
            Y.Assert.isTrue(function_called);
            ns.save = orig_save;
        },

        // Selecting a new private information type shows the
        // confirmation dialog and doesn't call save when user says 'no'.
        test_perform_update_information_type_to_private_no: function() {
            this._assert_save_with_validation_error();
            // The confirmation popup should be shown so stub out the save
            // method and check the behaviour.
            var orig_save = ns.save;
            var function_called = false;
            ns.save =
                    function(widget, initial_value, value, lp_client,
                             context, subscribers_list, validate_change) {
                // We only care if the function is called with
                // validate_change = false
                function_called = !validate_change;
            };
            // We click 'no' on the confirmation dialog.
            var co = Y.one('.yui3-overlay.yui3-lp-app-confirmationoverlay');
            var div = co.one('.yui3-lazr-formoverlay-actions');
            var ok = div.one('.cancel-btn');
            ok.simulate('click');
            // Original widget value, description etc should be retained.
            Y.Assert.areEqual('PUBLIC', this.widget.get('value'));
            var description_node = Y.one('#information-type-description');
            Y.Assert.areEqual(
                    'Public Description', description_node.get('text'));
            var summary = Y.one('#information-type-summary');
            Y.Assert.isFalse(summary.hasClass('private'));
            Y.Assert.isFalse(function_called);
            ns.save = orig_save;
        },

        // Test error handling when a save fails.
        test_information_type_save_error: function() {
            this.makeWidget();
            this.widget.set('value', 'USERDATA');
            ns.save(
                    this.widget, 'PUBLIC', 'USERDATA', this.lp_client,
                    LP.cache.bug);
            this.mockio.last_request.respond({
                status: 500,
                statusText: 'An error occurred'
            });
            // The original info type value from the cache should have been
            // set back into the widget.
            Y.Assert.areEqual('PUBLIC', this.widget.get('value'));
            var description_node = Y.one('#information-type-description');
            Y.Assert.areEqual(
                'Public Description', description_node.get('text'));
            var summary = Y.one('#information-type-summary');
            Y.Assert.isTrue(summary.hasClass('public'));
            // The error was displayed.
            Y.Assert.isNotNull(Y.one('.yui3-lazr-formoverlay-errors'));
        },

        test_change_event_empty: function () {
            // When firing a change event you must supply a value.
            Y.fire('information_type:change');
        },

        test_change_event_fires: function () {
            var called = false;
            var change_ev = Y.on('information_type:change', function (ev) {
                Y.Assert.areEqual('PUBLIC', ev.value);
                called = true;
            });

            Y.fire('information_type:change', {
                value: 'PUBLIC'
            });

            Y.Assert.isTrue(called, 'Did get a called event');

            // clean up our event since it's global to our Y instance.
            change_ev.detach();
        },

        test_change_public_event: function () {
            // If the value is a public value then the is_public event fires.
            var called = false;
            var public_ev = Y.on('information_type:is_public', function (ev) {
                Y.Assert.areEqual('PUBLIC', ev.value);
                called = true;
            });
            // However is should not fire an is_private event.
            var private_ev = Y.on('information_type:is_private', function (ev) {
                called = false;
            });

            Y.fire('information_type:change', {
                value: 'PUBLIC'
            });

            Y.Assert.isTrue(called, 'Did get a called event');

            // Clean up our event since it's global to our Y instance.
            public_ev.detach();
            private_ev.detach();
        },

        test_change_private_event: function () {
            // If the value is a private value then the is_private event fires.
            var called = false;

            // However is should not fire an is_private event.
            var public_ev = Y.on('information_type:is_public', function (ev) {
                called = false;
            });
            var private_ev = Y.on('information_type:is_private', function (ev) {
                Y.Assert.areEqual('PROPRIETARY', ev.value);
                Y.Assert.areEqual(
                    'This page contains Proprietary information.',
                    ev.text);
                called = true;
            });

            Y.fire('information_type:change', {
                value: 'PROPRIETARY'
            });

            Y.Assert.isTrue(called, 'Did get a called event');

            // Clean up our event since it's global to our Y instance.
            public_ev.detach();
            private_ev.detach();
        },

        test_private_security_is_private: function () {
            // A value of PRIVATESECURITY counts as a private event.
            var called = false;

            // However is should not fire an is_private event.
            var public_ev = Y.on('information_type:is_public', function (ev) {
                called = false;
            });
            var private_ev = Y.on('information_type:is_private', function (ev) {
                Y.Assert.areEqual('PRIVATESECURITY', ev.value);
                called = true;
            });

            Y.fire('information_type:change', {
                value: 'PRIVATESECURITY'
            });

            Y.Assert.isTrue(called, 'Did get a called event');

            // Clean up our event since it's global to our Y instance.
            public_ev.detach();
            private_ev.detach();
        },

        test_public_security_is_public: function () {
            // A value of PUBLICSECURITY counts as a public event.
            var called = false;

            // However is should not fire an is_private event.
            var public_ev = Y.on('information_type:is_public', function (ev) {
                Y.Assert.areEqual('PUBLICSECURITY', ev.value);
                called = true;
            });
            var private_ev = Y.on('information_type:is_private', function (ev) {
                called = false;
            });

            Y.fire('information_type:change', {
                value: 'PUBLICSECURITY'
            });

            Y.Assert.isTrue(called, 'Did get a called event');

            // Clean up our event since it's global to our Y instance.
            public_ev.detach();
            private_ev.detach();
        }
    }));

}, '0.1', {'requires': ['test', 'test-console', 'event', 'node-event-simulate',
        'lp.testing.mockio', 'lp.client', 'lp.app.information_type',
        'lp.bugs.subscribers']});
