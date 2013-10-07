/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */
YUI.add('lp.longpoll.test', function (Y) {
    var longpoll = Y.lp.app.longpoll;

    var suite = new Y.Test.Suite("longpoll Tests");
    var tests = Y.namespace('lp.longpoll.test');
    tests.suite = new Y.Test.Suite('longpoll Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'TestLongPollSingleton',
        tearDown: function() {
            // Cleanup the singleton;
            longpoll._manager = null;
        },

        testGetSingletonLongPollManager: function() {
            Y.Assert.isNull(longpoll._manager);
            var manager = longpoll.getLongPollManager();
            Y.Assert.isNotNull(longpoll._manager);
            var manager2 = longpoll.getLongPollManager();
            Y.Assert.areSame(manager, manager2);
        },

        testInitLongPollManagerNoLongPoll: function() {
            // if LP.cache.longpoll.key is undefined: no longpoll manager
            // is created by setupLongPollManager.
            window.LP = {
                links: {},
                cache: {}
            };

            longpoll.setupLongPollManager(true);
            Y.Assert.isNull(longpoll._manager);
        },

        testInitLongPollManagerLongPoll: function() {
            window.LP = {
                links: {},
                cache: {
                    longpoll: {
                        key: 'key',
                        uri: '/+longpoll/'
                    }
                }
            };

            longpoll.setupLongPollManager(true);
            Y.Assert.isNotNull(longpoll._manager);
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'TestLongPoll',

        setUp: function() {
            var manager = longpoll.getLongPollManager();
            manager._repoll = false;
            this.createBaseLP();
        },

        tearDown: function() {
            // Cleanup the singleton;
            longpoll._manager = null;
        },

        createBaseLP:function() {
            window.LP = {
                links: {},
                cache: {}
            };
        },

        setupLPCache: function() {
            LP.cache.longpoll = {
                key: 'key',
                uri: '/+longpoll/'
            };
        },

       setupLongPoll: function(nb_calls) {
            this.setupLPCache();
            return longpoll.setupLongPollManager(true);
        },

        testInitLongPollManagerQueueName: function() {
            var manager = this.setupLongPoll();
            Y.Assert.areEqual(LP.cache.longpoll.key, manager.key);
            Y.Assert.areEqual(LP.cache.longpoll.uri, manager.uri);
            Y.Assert.isFalse(Y.Lang.isValue(manager.nb_calls));
        },

        testPollStarted: function() {
            var fired = false;
            Y.on(longpoll.longpoll_start_event, function() {
                fired = true;
            });
            var manager = this.setupLongPoll();
            Y.Assert.isTrue(fired, "Start event not fired.");
        },

        testPollFailure: function() {
            var fired = false;
            Y.on(longpoll.longpoll_fail_event, function() {
                fired = true;
            });
            // Monkeypatch io to simulate failure.
            var manager = longpoll.getLongPollManager();
            manager._io = function(uri, config) {
                config.on.failure();
            };
            this.setupLongPoll();
            Y.Assert.isTrue(fired, "Failure event not fired.");
        },

        testSuccessPollInvalidData: function() {
            var manager = longpoll.getLongPollManager();
            var custom_response = "{{";
            var response = {
                responseText: custom_response
            };
            var res = manager.successPoll("2", response);
            Y.Assert.isFalse(res);
        },

        testSuccessPollMalformedData: function() {
            var manager = longpoll.getLongPollManager();
            var response = {
                responseText: '{ "something": "6" }'
            };
            var res = manager.successPoll("2", response);
            Y.Assert.isFalse(res);
         },

         testSuccessPollWellformedData: function() {
            var manager = longpoll.getLongPollManager();
            var response = {
                responseText: '{ "event_key": "4", "something": "6"}'
            };
            var res = manager.successPoll("2", response);
            Y.Assert.isTrue(res);
        },

        testPollDelay: function() {
            // Create event listeners.
            var longdelay_event_fired = false;
            Y.on(longpoll.longpoll_longdelay, function(data) {
                longdelay_event_fired = true;
            });
            var shortdelay_event_fired = false;
            Y.on(longpoll.longpoll_shortdelay, function(data) {
                shortdelay_event_fired = true;
            });
            var manager = longpoll.getLongPollManager();
            // Monkeypatch io to simulate failure.
            manager._io = function(uri, config) {
                config.on.failure();
            };
            Y.Assert.areEqual(0, manager._failed_attempts);
            this.setupLongPoll();
            Y.Assert.areEqual(1, manager._failed_attempts);
            var i, delay;
            for (i=0; i<longpoll.MAX_SHORT_DELAY_FAILED_ATTEMPTS-2; i++) {
                Y.Assert.areEqual(i+1, manager._failed_attempts);
                delay = manager._pollDelay();
                Y.Assert.areEqual(delay, longpoll.SHORT_DELAY);
            }
            // After MAX_SHORT_DELAY_FAILED_ATTEMPTS failed attempts, the
            // delay returned by _pollDelay is LONG_DELAY and
            // longpoll_longdelay is fired.
            Y.Assert.isFalse(longdelay_event_fired);
            delay = manager._pollDelay();
            Y.Assert.isTrue(longdelay_event_fired);
            Y.Assert.areEqual(delay, longpoll.LONG_DELAY);

            // Monkeypatch io to simulate success.
            manager._io = function(uri, config) {
                config.on.success();
            };
            // After a success, longpoll.longpoll_shortdelay is fired.
            Y.Assert.isFalse(shortdelay_event_fired);
            delay = manager.poll();
            Y.Assert.isTrue(shortdelay_event_fired);
        },

        testPollUriSequence: function() {
            // Each new polling increases the sequence parameter:
            // /+longpoll/?uuid=key&sequence=1
            // /+longpoll/?uuid=key&sequence=2
            // /+longpoll/?uuid=key&sequence=3
            // ..
            var count = 0;
            // Monkeypatch io to simulate failure.
            var manager = longpoll.getLongPollManager();
            manager._io = function(uri, config) {
                Y.Assert.areEqual(
                    '/+longpoll/?uuid=key&sequence=' + (count+1),
                    uri);
                count = count + 1;
                var response = {
                   responseText: '{"i":2}'
                };
                config.on.success(2, response);
            };
            this.setupLongPoll();
            var request;
            for (request=1; request<10; request++) {
                Y.Assert.isTrue(count === request, "Uri not requested.");
                manager.poll();
            }
        },

        _testDoesNotFail: function(error_code) {
            // Assert that, when the longpoll request receives an error
            // with code error_code, it is not treated as a failed
            // connection attempt.
            var manager = longpoll.getLongPollManager();
            // Monkeypatch io to simulate a request timeout.
            manager._io = function(uri, config) {
                response = {status: error_code};
                config.on.failure(4, response);
            };

            Y.Assert.areEqual(0, manager._failed_attempts);
            this.setupLongPoll();
            Y.Assert.areEqual(0, manager._failed_attempts);
        },

        test408RequestTimeoutHandling: function() {
            this._testDoesNotFail(408);
        },

        test504GatewayTimeoutHandling: function() {
            this._testDoesNotFail(504);
        },

        testPollPayLoadBad: function() {
            // If a non valid response is returned, longpoll_fail_event
            // is fired.
            var fired = false;
            Y.on(longpoll.longpoll_fail_event, function() {
                fired = true;
            });
            var manager = longpoll.getLongPollManager();
            // Monkeypatch io.
            manager._io = function(uri, config) {
                var response = {
                   responseText: "{non valid json"
                };
                config.on.success(2, response);
            };
            this.setupLongPoll();
            Y.Assert.isTrue(fired, "Failure event not fired.");
        },

        testPollPayLoadOk: function() {
            // Create a valid message.
            var custom_response = {
                'event_key': 'my-event',
                'something': {something_else: 1234}
            };
            var fired = false;
            Y.on(custom_response.event_key, function(data) {
                fired = true;
                Y.Assert.areEqual(data, custom_response);
            });
            var manager = longpoll.getLongPollManager();
            // Monkeypatch io.
            manager._io = function(uri, config) {
                var response = {
                   responseText: Y.JSON.stringify(custom_response)
                };
                config.on.success(2, response);
            };
            this.setupLongPoll();
            Y.Assert.isTrue(fired, "Custom event not fired.");
        }
    }));

}, '0.1', {
    requires: ['lp.testing.runner', 'test', 'test-console', 'node-event-simulate',
               'json', 'lp.app.longpoll']
});
