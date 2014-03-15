/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * The Launchpad DynamicDomUpdater module provides a plugin class that
 * can be plugged in to a DOM subtree, so that the subtree can update itself
 * regularly using the Launchpad API.
 *
 * @module soyuz
 * @submodule dynamic_dom_updater
 * @requires yahoo, node, plugin, LP
 */
YUI.add('lp.soyuz.dynamic_dom_updater', function(Y) {

var namespace = Y.namespace('lp.soyuz.dynamic_dom_updater');

    /**
     * The DomUpdater class provides the ability to plugin functionality
     * to a DOM subtree so that it can update itself when given data in an
     * expected format.
     *
     * For example:
     *     var table = Y.one('table#build-count-table');
     *     var config = {
     *         domUpdateFunction: updateArchiveBuildStatusSummary
     *     }
     *     table.plug(LP.DomUpdater, config);
     *
     *     // Now updating the table is as simple as:
     *     table.updater.update({total:3, failed: 1});
     *
     * @class DomUpdater
     * @extends Plugin
     * @constructor
     */
    var DomUpdater = function(config){
        DomUpdater.superclass.constructor.apply(this, arguments);
    };

    DomUpdater.NAME = 'domupdater';
    DomUpdater.NS = 'updater';

    DomUpdater.ATTRS = {
        /**
         * The function that updates the host's dom subtree.
         *
         * @attribute domUpdateFunction
         * @type Function
         * @default null
         */
        domUpdateFunction: {
            value: null
        }
    };

    Y.extend(DomUpdater, Y.Plugin.Base, {

        /**
         * The update method simply passes through to the user provided
         * update function.
         *
         * @method update
         * @param update_data {Object} The user defined data that will be
         *        passed to the users domUpdateFunction.
         */
        update: function(update_data) {
            Y.log("Updating Dom subtree for " + this.get("host"),
                  "info", "DomUpdater");
            var domUpdateFunction = this.get("domUpdateFunction");
            if (domUpdateFunction !== null){
                domUpdateFunction(this.get("host"), update_data);
            }
        }

    });

    /*
     * Ensure that the DomUpdater is available within the namespace.
     */
    namespace.DomUpdater = DomUpdater;

    /**
     * The DynamicDomUpdater class provides the ability to plug functionality
     * into a DOM subtree so that it can update itself using an LP api method.
     *
     * For example:
     *     var table = Y.one('table#build-count-table');
     *     var config = {
     *         domUpdateFunction: updateArchiveBuildStatusSummary,
     *         uri: LP.cache.context.self_link,
     *         api_method_name: 'getBuildCounters'
     *     }
     *     table.plug(LP.DynamicDomUpdater, config);
     *
     * Once configured, the 'table' dom subtree will now update itself
     * by calling the user defined domUpdateFunction (with a default interval
     * of 6000ms) with the result of the LPs api call.
     *
     * @class DynamicDomUpdater
     * @extends DomUpdater
     * @constructor
     */
    DynamicDomUpdater = function(config) {
        DynamicDomUpdater.superclass.constructor.apply(this, arguments);
    };
    DynamicDomUpdater.NAME = 'dynamicdomupdater';
    DynamicDomUpdater.NS = 'updater';
    DynamicDomUpdater.ATTRS = {
        /**
         * The uri to use for the LP.get request.
         *
         * @attribute uri
         * @type String
         */
        uri: {
            value: null
        },

        /**
         * The LP client to use. If none is provided, one will be
         * created during initialization.
         *
         * @attribute lp_client
         */
        lp_client: {
            value: null
        },

        /**
         * The LP api method name (if applicable).
         *
         * @attribute api_method_name
         * @type String
         */
        api_method_name: {
            value: null
        },

        /**
         * The function that provides the parameters for the API call.based
         * on the current state of the subtree.
         *
         * If this is not specified, no parameters will be included.
         *
         * @attribute parameterEvaluatorFunction
         * @type Function
         */
        parameterEvaluatorFunction: {
            value: null
        },

        /**
         * The interval (in ms) with which the subtree should be updated.
         *
         * @attribute interval
         * @type NUM
         * @default 60000
         */
        interval: {
            value: 60000
        },

        /**
         * The function used to determine whether updates should stop.
         *
         * If it is not included, we use a default function that always
         * returns false so the updates will continue infinitely.
         *
         * Once this function returns true, updates will stop and not
         * be restarted.
         *
         * @attribute stopUpdatesCheckFunction
         * @type Function
         */
        stopUpdatesCheckFunction: {
            value: function(data){return false;}
        },

        /**
         * The interval (in ms) that is considered too long for processing
         * the LP api request.
         *
         * If requests to the LP API are taking more than this number of
         * milliseconds, then the poll interval will be doubled.
         */
        long_processing_time: {
            value: 5000
        },

        /**
         * The interval (in ms) that is considered very short for processing
         * the LP api request.
         *
         * If requests to the LP API are completing in less than this number
         * of milliseconds, then the poll interval will be halved (as long
         * as this does not make the poll interval less than the original
         * requested interval).
         */
        short_processing_time: {
            value: 1000
        }

    };

    Y.extend(DynamicDomUpdater, DomUpdater, {
        /**
         * The initializer method that is called from the base Plugin class.
         *
         * @method initializer
         * @protected
         */
        initializer: function(){
            Y.log("Initializing updater for " + this.get("host") +
                  " with an interval of " + this.get("interval") + "ms.",
                  "info", "LPDynamicDomUpdater");

            // Create the configuration for the LP client request:
            this._lp_api_config = {
                on: {
                    success: Y.bind(this._handleSuccess, this),
                    failure: Y.bind(this._handleFailure, this)
                }
            };

            // Set the actual interval based on the interval attribute.
            this._actual_interval = this.get('interval');

            // If we have not been provided with a Launchpad Client, then
            // create one now:
            if (null === this.get("lp_client")){
                // Create our own instance of the LP client.
                this.set("lp_client", new Y.lp.client.Launchpad());
            }

            setTimeout(
                Y.bind(this.dynamicUpdate, this),
                this._actual_interval);
        },

        /**
         * The dynamicUpdate method is responsible for updating the DOM
         * subtree with data from a dynamic source.
         *
         * @method dynamicUpdate
         */
        dynamicUpdate: function() {
            Y.log("Starting update for " + this.get("host"),
                  "info", "LP.DynamicDomUpdater");
            var uri = this.get("uri");
            var api_method_name = this.get("api_method_name");

            // Check whether we should stop updating now...
            if (this.get("stopUpdatesCheckFunction")(this.get("host"))){
                Y.log(
                    "Cancelling updates for " + this.get("host") +
                    "after stopUpdatesCheckFunction returned true.", "info",
                    "LP DynamicDomUpdater");
                return;
            }

            // Set any parameters for the API call:
            var parameterEvaluatorFunction = this.get(
                "parameterEvaluatorFunction");
            if (parameterEvaluatorFunction !== null){
                this._lp_api_config.parameters = parameterEvaluatorFunction(
                    this.get("host"));
            }

            // Finally, call the LP api method as required...
            if (uri) {
                if (api_method_name) {
                    this.get("lp_client").named_get(uri,
                        api_method_name, this._lp_api_config);
                }
                else {
                    this.get("lp_client").get(uri, this._lp_api_config);
                }
            }

            // Record the time when the request started so we can
            // evaluate the elapsed time for the request.
            this._request_start = new Date().getTime();
        },

        /**
         * Update our actual poll interval depending on the elapsed time
         * for this request.
         *
         * @method _updateActualInterval
         * @private
         */
        _updateActualInterval: function(elapsed_time) {
            if (elapsed_time > this.get('long_processing_time')) {
                this._actual_interval *= 2;
                return true;
            }
            if (elapsed_time < this.get('short_processing_time')) {
                var new_actual_interval = this._actual_interval / 2;

                // If the newly-calculated actual interval is greater than
                // the config interval then we update to the new interval,
                // otherwise if the actual interval is currently greater
                // than the config interval, then we update to the config
                // interval.
                var config_interval = this.get('interval');
                if (new_actual_interval >= config_interval) {
                    this._actual_interval = new_actual_interval;
                    return true;
                } else if (this._actual_interval > config_interval){
                    this._actual_interval = config_interval;
                    return true;
                }
            }
            return false;
        },

        /**
         * Success handler for the call to the LP API.
         *
         * @method _handleSuccess
         * @private
         */
        _handleSuccess: function(data) {
            var elapsed_time = new Date().getTime() - this._request_start;
            Y.log([
                "Data received for ",
                this.get("host"),
                " after ",
                elapsed_time,
                "ms."
                ].join(""), "info", "LP.DynamicDomUpdater");

            // Call our parent class's update method to update the DOM
            // subtree with the returned data.
            this.update(data);

            // Update our actual poll interval.
            var actual_interval_updated = this._updateActualInterval(
                elapsed_time)
            if (actual_interval_updated) {
                Y.log("Actual poll interval updated to " +
                    this._actual_interval + "ms.");
            }

            // As the previous request was successful, request the next one.
            setTimeout(
                Y.bind(this.dynamicUpdate, this),
                this._actual_interval);
        },

        /**
         * Failure handler for the call to the LP API.
         *
         * @method _handleFailure
         * @private
         */
        _handleFailure: function(id, request) {
            Y.error("LP.DynamicDomUpdater for " + this.get("host") +
                    " failed to get dynamic data.");
        }
    });

    /*
     * Ensure that the DynamicDomUpdater is available within the namespace.
     */
    namespace.DynamicDomUpdater = DynamicDomUpdater;

}, "0.1", {"requires":["node", "plugin", "lp.client"]});
