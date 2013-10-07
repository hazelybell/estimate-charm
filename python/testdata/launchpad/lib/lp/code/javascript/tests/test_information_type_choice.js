/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.code.branch.information_type_choice.test', function (Y) {

    var tests = Y.namespace('lp.code.branch.information_type_choice.test');
    var ns = Y.lp.code.branch.information_type_choice;
    var info_type = Y.lp.app.information_type;

    tests.suite = new Y.Test.Suite(
            'lp.code.branch.information_type_choice Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'lp.code.branch.information_type_choice_tests',

        setUp: function() {
            window.LP = {
                cache: {
                    context: {
                        web_link: '',
                        information_type: 'Public'
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
                            description: 'Public Security Description'},
                        PROPRIETARY: {
                            value: 'PROPRIETARY', name: 'Proprietary',
                            is_private: true, order: 3,
                            description: 'Private Description'},
                        USERDATA: {
                            value: 'USERDATA', name: 'Private',
                            is_private: true, order: 4,
                            description: 'Private Description'}
                    }
                }
            };
            this.fixture = Y.one('#fixture');
            var portlet = Y.Node.create(
                    Y.one('#portlet-template').getContent());
            this.fixture.appendChild(portlet);
            this.mockio = new Y.lp.testing.mockio.MockIo();
        },

        tearDown: function () {
            if (this.fixture !== null) {
                this.fixture.empty(true);
            }
            delete this.fixture;
            delete this.mockio;
            delete window.LP;
        },

        makeWidget: function() {
            this.widget = new ns.BranchInformationTypeWidget({
                io_provider: this.mockio,
                use_animation: false
            });
            this.widget.render();
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.code.branch.information_type_choice,
                "Cannot locate the " +
                "lp.code.branch.information_type_choice module");
        },

        // The widget is created as expected.
        test_create_widget: function() {
            this.makeWidget();
            Y.Assert.isInstanceOf(
                ns.BranchInformationTypeWidget, this.widget,
                "Branch info type widget failed to be instantiated");
            var privacy_link = Y.one('#privacy-link');
            Y.Assert.isTrue(privacy_link.hasClass('js-action'));
        },

        // The save XHR call works as expected.
        test_save_information_type: function() {
            this.makeWidget();
            var save_success_called = false;
            this.widget._information_type_save_success = function(value) {
                Y.Assert.areEqual('USERDATA', value);
                save_success_called = true;
            };
            this.widget._save_information_type('USERDATA');
            this.mockio.success({
                responseText: '',
                responseHeaders: {'Content-Type': 'application/json'}});
            Y.Assert.areEqual(
                document.URL + '/+edit-information-type',
                this.mockio.last_request.url);
            Y.Assert.areEqual(
                'field.actions.change=Change%20Branch&' +
                'field.information_type=USERDATA',
                this.mockio.last_request.config.data);
            Y.Assert.isTrue(save_success_called);
        },

        // Setting a private type shows the privacy banner.
        test_information_type_save_success_private: function() {
            var fired = false;
            Y.on(info_type.EV_ISPRIVATE, function (ev) {
                fired = true;
            });

            this.makeWidget();

            this.widget._information_type_save_success('PROPRIETARY');
            Y.Assert.isTrue(fired);
            Y.Assert.areEqual(
                'Proprietary', LP.cache.context.information_type);
        },

        // Setting a private type hides the privacy banner.
        test_information_type_save_success_public: function() {
            var fired = false;
            Y.on(info_type.EV_ISPUBLIC, function (ev) {
                fired = true;
            });

            this.makeWidget();

            this.widget._information_type_save_success('PUBLIC');
            Y.Assert.isTrue(fired);
            Y.Assert.areEqual('Public', LP.cache.context.information_type);
        },

        // Test error handling when a save fails.
        test_information_type_save_error: function() {
            this.makeWidget();
            this.widget.information_type_edit.set('value', 'USERDATA');
            this.widget._save_information_type('USERDATA');
            this.mockio.last_request.respond({
                status: 500,
                statusText: 'An error occurred'
            });
            // The original info type value from the cache should have been
            // set back into the widget.
            Y.Assert.areEqual(
                    'PUBLIC',
                    this.widget.information_type_edit.get('value'));
            var description_node = Y.one('#information-type-description');
            Y.Assert.areEqual(
                'Public Description', description_node.get('text'));
            var summary = Y.one('#information-type-summary');
            Y.Assert.isTrue(summary.hasClass('public'));
            // The error was displayed.
            Y.Assert.isNotNull(Y.one('.yui3-lazr-formoverlay-errors'));
        }
    }));

}, '0.1', {'requires': ['test', 'test-console', 'event', 'node-event-simulate',
        'lp.testing.mockio', 'lp.client', 'lp.app.information_type',
        'lp.code.branch.information_type_choice']});
