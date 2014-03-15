/**
 * Copyright 2011 Canonical Ltd. This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Tests for Extras.
 *
 * @module lp.extras
 * @submodule test
 */

YUI.add('lp.extras.test', function(Y) {

    var namespace = Y.namespace('lp.extras.test');

    var Assert = Y.Assert;
    var ArrayAssert = Y.ArrayAssert;

    var suite = new Y.Test.Suite("extras Tests");
    var extras = Y.lp.extras;

    var TestNodeListMap = {
        name: 'TestNodeListMap',

        test_static: function() {
            var nodes = [
                Y.Node.create("<div />"),
                Y.Node.create("<label />"),
                Y.Node.create("<strong />")
            ];
            ArrayAssert.itemsAreSame(
                nodes,
                Y.NodeList.map(
                    nodes, function(node) { return node; })
            );
            ArrayAssert.itemsAreSame(
                ["DIV", "LABEL", "STRONG"],
                Y.NodeList.map(nodes, function(node) {
                    return node.get("tagName");
                })
            );
        },

        test_static_with_DOM_nodes: function() {
            // NodeList.map converts DOM nodes into Y.Node instances.
            var nodes = [
                document.createElement("div"),
                document.createElement("label"),
                document.createElement("strong")
            ];
            Y.NodeList.map(nodes, function(node) {
                Assert.isInstanceOf(Y.Node, node);
            });
            ArrayAssert.itemsAreSame(
                ["DIV", "LABEL", "STRONG"],
                Y.NodeList.map(nodes, function(node) {
                    return node.get("tagName");
                })
            );
        },

        test_method: function() {
            var nodes = [
                Y.Node.create("<div />"),
                Y.Node.create("<label />"),
                Y.Node.create("<strong />")
            ];
            var nodelist = new Y.NodeList(nodes);
            ArrayAssert.itemsAreSame(
                nodes,
                nodelist.map(function(node) { return node; })
            );
            ArrayAssert.itemsAreSame(
                ["DIV", "LABEL", "STRONG"],
                nodelist.map(function(node) {
                    return node.get("tagName");
                })
            );
        }

    };

    var TestAttributeFunctions = {
        name: 'TestAttributeFunctions',

        test_attrgetter: function() {
            var subject = {foo: 123, bar: 456};
            Assert.areSame(123, extras.attrgetter("foo")(subject));
            Assert.areSame(456, extras.attrgetter("bar")(subject));
        },

        test_attrselect: function() {
            var subject = [
                {foo: 1, bar: 5},
                {foo: 3, bar: 7},
                {foo: 2, bar: 6},
                {foo: 4, bar: 8}
            ];
            ArrayAssert.itemsAreSame(
                [1, 3, 2, 4], extras.attrselect("foo")(subject));
            ArrayAssert.itemsAreSame(
                [5, 7, 6, 8], extras.attrselect("bar")(subject));
        },

        test_attrcaller: function() {
            var subject = [
                {foo: function(num) { return num + 1; }},
                {foo: function(num) { return num + 2; }},
                {foo: function(num) { return num + 3; }}
            ];
            ArrayAssert.itemsAreSame(
                [4, 5, 6], subject.map(extras.attrcaller("foo", 3)));
        }

    };

    // Populate the suite.
    suite.add(new Y.Test.Case(TestNodeListMap));
    suite.add(new Y.Test.Case(TestAttributeFunctions));

    // Exports.
    namespace.suite = suite;

}, "0.1", {requires: ["test", "lp.extras"]});
