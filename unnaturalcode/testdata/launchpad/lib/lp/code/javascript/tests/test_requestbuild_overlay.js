/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */
YUI.add('lp.requestbuild_overlay.test', function (Y) {
var module = Y.lp.code.requestbuild_overlay;

var tests = Y.namespace('lp.requestbuild_overlay.test');
tests.suite = new Y.Test.Suite("lp.code.requestbuild_overlay Tests");

var builds_target_markup = Y.one('#builds-target-template').getContent(),
    requestform_markup = Y.one('#requestbuilds-form-template').getContent();

tests.suite.add(new Y.Test.Case({
    name: "lp.code.requestbuild_overlay.requestdailybuild",

    setUp: function() {
        LP.cache.context = {
            web_link: "http://code.launchpad.dev/~foobar/myrecipe"};
        // Prepare testbed.
        fixture = Y.one("#testbed");
        var template = Y.one('#build-schedule-template').getContent();
        var test_node = Y.Node.create(template);
        fixture.append(test_node);
    },

    tearDown: function() {
        Y.one("#testbed").empty();
        LP.cache.context = {};
        LP.cache.links = {};
    },


    _makeRequest: function() {
        var mockio = new Y.lp.testing.mockio.MockIo();
        var build_now_link = Y.one('#request-daily-build');
        build_now_link.removeClass('hidden');
        module.connect_requestdailybuild({io_provider: mockio});
        build_now_link.simulate('click');

        Y.Assert.areSame(1, mockio.requests.length);
        return mockio;
    },

    test_requestdailybuild_success: function() {
        var mockio = this._makeRequest();
        mockio.success({
            responseText: builds_target_markup,
            responseHeaders: {'Content-Type': 'application/xhtml'}
        });

        // The markup has been inserted.
        Y.Assert.areSame(
            2, Y.one("#builds-target").all('.package-build').size());
        // The message is being displayed as informational.
        var info = Y.one("#new-builds-info");
        Y.Assert.isTrue(info.hasClass('build-informational'));
        Y.Assert.areSame(
            "2 new recipe builds have been queued.Dismiss",
            info.get('text'));
        // The message can be dismissed.
        info.one('a').simulate('click');
        Y.Assert.areSame('none', info.getStyle('display'));
        // The build now button is hidden.
        Y.Assert.isTrue(Y.one('#request-daily-build').hasClass('hidden'));
    },


    _testRequestbuildFailure: function(status, expected_message, oops) {
        var mockio = this._makeRequest(),
            response = {status: status},
            error;
        if (oops !== undefined) {
            response.responseHeaders = {'X-Lazr-OopsId': oops};
        }
        mockio.respond(response);

        // No build targets.
        Y.Assert.areSame(
            0, Y.one("#builds-target").all('.package-build').size());
        // The message is being displayed as an error.
        error = Y.one("#new-builds-info");
        Y.Assert.isTrue(error.hasClass('build-error'));
        Y.Assert.areSame(expected_message + "Dismiss", error.get('text'));
        // The message can be dismissed.
        error.one('a').simulate('click');
        Y.Assert.areSame('none', error.getStyle('display'));
        // The build now button stays visible.
        Y.Assert.isFalse(Y.one('#request-daily-build').hasClass('hidden'));
    },


    test_requestdailybuild_failure_503: function() {
        this._testRequestbuildFailure(
           503, "Timeout error, please try again in a few minutes.");
    },

    test_requestdailybuild_failure_500: function() {
        var oops_id = "OOPS-TESTING",
            message = "Server error, please contact an administrator. " +
                "OOPS ID:" + oops_id;
        this._testRequestbuildFailure(500, message, oops_id);
    }

}));

tests.suite.add(new Y.Test.Case({
    name: "lp.code.requestbuild_overlay.requestbuild",

    setUp: function() {
        LP.cache.context = {
            web_link: "http://code.launchpad.dev/~foobar/myrecipe",
            self_link: "http://api.launchpad.dev/devel/~foobar/myrecipe"};
        // Prepare testbed.
        fixture = Y.one("#testbed");
        var template = Y.one('#build-schedule-template').getContent();
        var test_node = Y.Node.create(template);
        fixture.append(test_node);
    },

    tearDown: function() {
        module.destroy_requestbuilds();
        Y.one("#testbed").empty();
        LP.cache.context = {};
        LP.cache.links = {};
    },

    _makeRequest: function() {
        var mockio = new Y.lp.testing.mockio.MockIo(),
            request_builds_link = Y.one('#request-builds'),
            submit_button;
        module.connect_requestbuilds({io_provider: mockio});
        request_builds_link.simulate('click');

        // The form overlay requests the form from the server.
        Y.Assert.areSame(1, mockio.requests.length);
        mockio.success({
            responseText: requestform_markup,
            responseHeaders: {'Content-Type': 'application/xhtml'}
        });
        // It checks for pending builds using the LP client.
        Y.Assert.areSame(2, mockio.requests.length);
        Y.Assert.areSame(
            "ws.op=getPendingBuildInfo", mockio.last_request.config.data);
        // This response is not really needed for the test.
        mockio.success({
            responseText: "[]",
            responseHeaders: {'Content-Type': 'application/json'}
        });
        // Submit the form.
        submit_button = Y.one("[name='field.actions.request']");
        submit_button.simulate('click');
        Y.Assert.areSame(3, mockio.requests.length);

        return mockio;
    },

    test_requestbuilds_success: function() {
        var mockio = this._makeRequest();
        mockio.success({
            responseText: builds_target_markup,
            responseHeaders: {'Content-Type': 'application/xhtml'}
        });

        // The form is hidden and the builds are displayed.
        Y.Assert.isTrue(
            Y.one(".yui3-lazr-formoverlay")
             .hasClass("yui3-lazr-formoverlay-hidden"));
        Y.Assert.areSame(
            2, Y.one("#builds-target").all('.package-build').size());
    },

    test_requestbuilds_failure_500: function() {
        var mockio = this._makeRequest(),
            oops_id = "OOPS-TESTING",
            message = "Server error, please contact an administrator. " +
                "OOPS ID:" + oops_id;
        mockio.failure({
            'responseHeaders': {'X-Lazr-OopsId': oops_id}
            });

        // The form stays visible and no builds are displayed.
        Y.Assert.isFalse(
            Y.one(".yui3-lazr-formoverlay")
             .hasClass("yui3-lazr-formoverlay-hidden"));
        Y.Assert.areSame(
            0, Y.one("#builds-target").all('.package-build').size());
        // The error message is displayed.
        Y.Assert.areSame(
            message,
            Y.one(".yui3-lazr-formoverlay-errors li").get('text'));
        // The submit button is disabled.
        Y.Assert.isTrue(
            Y.one("[name='field.actions.request']").get('disabled'));
    },

    test_requestbuilds_build_collision: function() {
        var mockio = this._makeRequest(),
            success_message = "2 new recipe builds have been queued.",
            informational_message = "An identical build ...",
            error_message = "Please specify a ...",
            response_text = {
                builds: builds_target_markup,
                already_pending: informational_message,
                errors: [error_message]
            };
        mockio.success({
            statusText: "Request Build",
            responseText: Y.JSON.stringify(response_text),
            responseHeaders: {'Content-type': 'application/json'}
            });

        // The form stays visible and the builds are displayed.
        Y.Assert.isFalse(
            Y.one(".yui3-lazr-formoverlay")
             .hasClass("yui3-lazr-formoverlay-hidden"));
        Y.Assert.areSame(
            2, Y.one("#builds-target").all('.package-build').size());
        // The informational message is displayed.
        Y.Assert.areSame(
            success_message + informational_message,
            Y.one(
                ".yui3-lazr-formoverlay-errors .popup-build-informational")
                .get('text'));
        // The error message is displayed.
        Y.Assert.areSame(
            error_message,
            Y.one(".yui3-lazr-formoverlay-errors li").get('text'));
        // The submit button is disabled.
        Y.Assert.isTrue(
            Y.one("[name='field.actions.request']").get('disabled'));
    }
}));


tests.suite.add(new Y.Test.Case({
    name: "lp.code.requestbuild_overlay.buildschedule",

    setUp: function() {
        fixture = Y.one("#testbed");
        var template = Y.one('#build-schedule-template').getContent();
        var test_node = Y.Node.create(template);
        fixture.append(test_node);
    },

    tearDown: function() {
        Y.one("#testbed").empty();
        LP.cache.context = {};
        LP.cache.links = {};
    },

    test_hookUpDailyBuildsSchedule_anonymous: function() {
        module.hookUpDailyBuildsSchedule();
        Y.Assert.isTrue(
            Y.one('#request-daily-build-form').hasClass('hidden'));
        Y.Assert.isTrue(
            Y.one('#request-daily-build').hasClass('hidden'));
    },

    test_hookUpDailyBuildsSchedule_logged_in_user: function() {
        LP.links.me = '/~name16';
        module.hookUpDailyBuildsSchedule();
        Y.Assert.isTrue(
            Y.one('#request-daily-build-form').hasClass('hidden'));
        Y.Assert.isFalse(
            Y.one('#request-daily-build').hasClass('hidden'));
    },

    test_hookUpDailyBuildsSchedule_without_form: function() {
        var form = Y.one('#request-daily-build-form');
        form.get('parentNode').removeChild(form);
        module.hookUpDailyBuildsSchedule();
        Y.Assert.isFalse(
            Y.one('#request-daily-build').hasClass('hidden'));
    }
}));


}, '0.1', {
    requires: ['test', 'test-console', 'node-event-simulate', 'json-stringify',
               'lp.testing.mockio', 'lp.testing.runner',
               'lp.code.requestbuild_overlay']
});
