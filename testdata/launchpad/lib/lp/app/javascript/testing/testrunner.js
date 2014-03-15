/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

var YUI_config = {
    filter: 'raw',
    combine: false,
    fetchCSS: false
};

YUI.add("lp.testing.runner", function(Y) {

/**
 * Testing utilities.
 *
 * @module lp.testing
 * @namespace lp
 */

var Runner = Y.namespace("lp.testing.Runner");

Runner.run = function(suite) {

    // Lock, stock, and two smoking barrels.
    var handle_complete = function(data) {
        window.status = '::::' + JSON.stringify({
            results: data.results,
            type: data.type
        });
    };
    Y.Test.Runner.on('complete', handle_complete);
    Y.Test.Runner.add(suite);

    Y.on("domready", function() {
        var log = Y.Node.create('<div></div>');
        Y.one(document.body).appendChild(log);

        var yconsole = new Y.Test.Console({
            filters: {
                pass: true,
                fail: true
            },
            newestOnTop: false,
            useBrowserConsole: true
        });
        yconsole.render(log);
        Y.Test.Runner.run();
    });
};

}, "0.1", {"requires": ["oop", "test", "test-console"]});


/**
 * Merely loading this script into a page will cause it to look for a
 * list of suites in the document using the selector ul#suites>li. If
 * found, the text within each node is considered to be a test module
 * name. This is then loaded, and its "suite" property passed to
 * Runner.run().
 *
 * Here's how to declare the suites to run:
 *
 *   <ul id="suites">
 *     <li>lp.registry.distroseries.initseries.test</li>
 *   </ul>
 *
 */
YUI().use("event", function(Y) {
    Y.on("domready", function() {
        var suites = Y.all("ul#suites > li");
        Y.each(suites, function(suite_node) {
            var suite_name = suite_node.get("text");
            Y.use("lp.testing.runner", suite_name, function(y) {
                var module = y, parts = suite_name.split(".");
                while (parts.length > 0) {
                    module = module[parts.shift()];
                }
                y.lp.testing.Runner.run(module.suite);
            });
        });
    });
});
