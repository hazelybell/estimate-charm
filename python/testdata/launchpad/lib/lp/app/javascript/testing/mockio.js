/* Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.testing.mockio', function(Y) {
    /**
     * A utility module for use in YUI unit-tests with a helper for
     * mocking Y.io.
     *
     * @module lp.testing.mockio
     */
    var namespace =  Y.namespace("lp.testing.mockio");

    var MockHttpResponse = function(config) {
        if (config === undefined) {
            config = {};
        }
        if (config.status !== undefined) {
            this.status = config.status;
        } else {
            this.status = 200;
        }
        if (config.statusText !== undefined) {
            this.statusText = config.statusText;
        } else {
            if (this.isFailure()) {
                this.statusText = "Internal Server Error";
            } else {
                this.statusText = "OK";
            }
        }
        if (config.responseText !== undefined) {
            this.responseText = config.responseText;
        } else {
            this.responseText = '[]';
        }
        if (config.responseHeaders !== undefined) {
            this.responseHeaders = config.responseHeaders;
        } else {
            this.responseHeaders = {};
        }
    };

    MockHttpResponse.prototype = {
        isFailure: function () {
            return this.status >= 400;
        },

        setResponseHeader: function (header, value) {
            this.responseHeaders[header] = value;
        },

        getResponseHeader: function(header) {
            return this.responseHeaders[header];
        }
    };
    namespace.MockHttpResponse = MockHttpResponse;

    function MockHttpRequest(url, config){
        this.url = url;
        this.config = config;
        this.response = null;
    }

    /* Simulate the Xhr request/response cycle. */
    MockHttpRequest.prototype.respond = function(response_config) {
        var context = this.config.context || Y,
            args = this.config['arguments'] || [],
            tId = 'mockTId',
            response = this.response = new MockHttpResponse(response_config);

        // See the Y.io utility documentation for the signatures.
        if (this.config.on.end !== undefined) {
            this.config.on.end.call(tId, args);
        }
        if (this.config.on.complete !== undefined) {
            this.config.on.complete.call(context, tId, response, args);
        }
        if (this.config.on.success !== undefined && !response.isFailure()) {
            this.config.on.success.call(context, tId, response, args);
        }
        if (this.config.on.failure !== undefined && response.isFailure()) {
            this.config.on.failure.call(context, tId, response, args);
        }
    };

    /**
     * Provide a successful JSON response
     *
     * @method successJSON
     * @param {Object} json_data JSON-serializable data to provide as the
     * response.
     */
    MockHttpRequest.prototype.successJSON = function(json_data){
        this.respond({
            responseText: Y.JSON.stringify(json_data),
            responseHeaders: {'Content-Type': 'application/json'}
        });
    };

    namespace.MockHttpRequest = MockHttpRequest;

    var MockIo = function() {
        this.requests = [];
        this.last_request = null;
    };

    /* Save the Y.io() arguments. */
    MockIo.prototype.io = function(url, config) {
        // See the Y.io utility documentation for the signatures.
        if (config.on.start !== undefined) {
            config.on.start.call('mockTId', config['arguments'] || []);
        }
        this.last_request = new MockHttpRequest(url, config);
        this.requests.push(this.last_request);
        return this;  // Usually this isn't used, except for logging.
    };

    /* Call respond method on last_request. */
    MockIo.prototype.respond = function(response_config) {
        this.last_request.respond(response_config);
    };

    /* Call respond method with successful values. */
    MockIo.prototype.success = function(config) {
        if (config === undefined) {
            config = {};
        }
        if (config.status === undefined || config.status >= 400) {
            config.status = 200;
        }
        config.statusText = 'OK';
        this.respond(config);
    };

    /* Call respond method with failed values. */
    MockIo.prototype.failure = function(config) {
        if (config === undefined) {
            config = {};
        }
        if (config.status === undefined || config.status < 400) {
            config.status = 500;
        }
        config.statusText = 'Internal Server Error';
        this.respond(config);
    };

    namespace.MockIo = MockIo;

}, '0.1', {});
