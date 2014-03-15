/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.testing.helpers', function(Y) {

    var ns = Y.namespace('lp.testing.helpers');


    /**
     * Reset the window history state.
     *
     * Useful for tearDown for code that modifies and stores data into the
     * History.state.
     * @function
     */
    ns.reset_history = function () {
        var win = Y.config.win;
        var originalURL = (win && win.location.toString()) || '';
        win.history.replaceState(null, null, originalURL);
    };


    /**
     * Testing mock for lp.client.
     *
     * Useful for testing calls to lp.client in other code, though it requires
     * the other code be setup so that it can accept a passed in client.
     *
     * USAGE: LPClient calls have two sets of 'args'. There are the args you pass
     * into the function call (e.g. `client.get(args)`) and the args set on
     * the callee (e.g. client.get.args). The latter must be set or an error
     * is thrown, though it can be set to nothing.
     *
     * EXAMPLE:
     *  var client = new ns.LPCLient();
     *
     *  client.get.args = [];
     *  client.get(function_arg1, function_arg2);
     */
    ns.LPClient = function () {
        if (!(this instanceof ns.LPClient)) {
            throw new Error("Constructor called as a function");
        }
        this.received = [];
        // LPClient provides mocks of the lp.client calls
        // Simulates a call to Y.lp.client.named_post
        this.named_post = function(url, func, config) {
            this._call('named_post', config, arguments);
        };
        // Simulates a PATCH call through Y.lp.client
        this.patch = function(bug_filter, data, config) {
            this._call('patch', config, arguments);
        };
        // Simulates a GET call through Y.lp.client
        this.get = function(url, config) {
            this._call('get', config, arguments);
        };
    }
    /**
     * Captures call data and simulates callbacks.
     *
     * The function called and the arguments it's called with are added to the
     * LPCLient's `received` attribute.
     *
     * Callback behavior are governed by the args set on the callee.
     * @method
     */
    ns.LPClient.prototype._call = function(name, config, args) {
        this.received.push(
            [name, Array.prototype.slice.call(args)]);
        if (!Y.Lang.isValue(args.callee.args)) {
            throw new Error("Set call_args on "+name);
        }
        var do_action = function () {
            if (Y.Lang.isValue(args.callee.fail) && args.callee.fail) {
                config.on.failure.apply(undefined, args.callee.args);
            } else {
                config.on.success.apply(undefined, args.callee.args);
            }
        };
        if (Y.Lang.isValue(args.callee.halt) && args.callee.halt) {
            args.callee.resume = do_action;
        } else {
            do_action();
        }
    };

}, '0.1', {
    'requires': [ 'history']
});
