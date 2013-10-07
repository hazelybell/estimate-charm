/**
 * Copyright 2011 Canonical Ltd. This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Tests for DistroSeries Differences.
 *
 * @module lp.registry.distroseries.differences
 * @submodule test
 */

YUI.add('lp.registry.distroseries.differences.test', function(Y) {

    var namespace = Y.namespace('lp.registry.distroseries.differences.test');

    var Assert = Y.Assert;
    var ArrayAssert = Y.ArrayAssert;

    var suite = new Y.Test.Suite("distroseries.differences Tests");
    var differences = Y.lp.registry.distroseries.differences;

    var TestFunctions = {
        name: "TestFunctions",

        test_get_packagesets_in_query: function() {
            Assert.isFunction(namespace.get_packagesets_in_query);
        },

        test_get_packagesets_in_query_no_matching_parameters: function() {
            ArrayAssert.itemsAreSame(
                [], namespace.get_packagesets_in_query(""));
            ArrayAssert.itemsAreSame(
                [], namespace.get_packagesets_in_query("?"));
            ArrayAssert.itemsAreSame(
                [], namespace.get_packagesets_in_query("?foo=bar"));
        },

        test_get_packagesets_in_query_matching_parameters: function() {
            ArrayAssert.itemsAreSame(
                ["foo"], namespace.get_packagesets_in_query(
                    "field.packageset=foo"));
            // A leading question mark is okay.
            ArrayAssert.itemsAreSame(
                ["foo"], namespace.get_packagesets_in_query(
                    "?field.packageset=foo"));
            ArrayAssert.itemsAreSame(
                ["foo", "bar"], namespace.get_packagesets_in_query(
                    "?field.packageset=foo&field.packageset=bar"));
        },

        test_get_packagesets_in_query_numeric_parameters: function() {
            // All-digit parameters are still returned as strings.
            ArrayAssert.itemsAreSame(
                ["123"], namespace.get_packagesets_in_query(
                    "field.packageset=123"));
        },

        test_get_changed_by_in_query: function() {
            Assert.isFunction(namespace.get_changed_by_in_query);
        },

        test_get_changed_by_in_query_no_matching_parameters: function() {
            Assert.isNull(namespace.get_changed_by_in_query(""));
            Assert.isNull(namespace.get_changed_by_in_query("?"));
            Assert.isNull(namespace.get_changed_by_in_query("?foo=bar"));
        },

        test_get_changed_by_in_query_matching_parameters: function() {
            Assert.areSame(
                "foo", namespace.get_changed_by_in_query(
                    "field.changed_by=foo"));
            // A leading question mark is okay.
            Assert.areSame(
                "foo", namespace.get_changed_by_in_query(
                    "?field.changed_by=foo"));
            // Only the first changed_by parameter is returned.
            Assert.areSame(
                "foo", namespace.get_changed_by_in_query(
                    "?field.changed_by=foo&field.changed_by=bar"));
        },

        test_linkify: function() {
            var target = Y.Node.create("<div>Foobar</div>");
            var link = namespace.linkify(target);
            Assert.isInstanceOf(Y.Node, link);
            Assert.areSame(link, target.one("a"));
            Assert.areSame("Foobar", link.get("text"));
            Assert.isTrue(link.hasClass("js-action"));
            var href = link.get("href");
            Assert.isString(href);
            Assert.isTrue(href.length > 0);
        }

    };

    suite.add(new Y.Test.Case(TestFunctions));

    var TestLastChangedPicker = {
        name: "TestLastChangedPicker",

        setUp: function() {
            window.LP = {
                links: {
                    me: "~foobar"
                }
            };
            var body = Y.one(document.body);
            this.form = Y.Node.create("<form />").appendTo(body);
            this.origin = Y.Node.create("<div>Origin</div>").appendTo(body);
            this.picker = differences.connect_last_changed_picker(
                this.origin, this.form);
        },

        tearDown: function() {
            this.picker.get("boundingBox").remove(true);
            this.origin.remove(true);
            this.form.remove(true);
            delete window.LP;
        },

        test_linkify_click_activates_picker: function() {
            Assert.isFalse(this.picker.get("visible"));
            this.origin.one("a").simulate("click");
            Assert.isTrue(this.picker.get("visible"));
        },

        test_picker_save_updates_and_submits_form: function() {
            var submitted = false;
            this.form.submit = function(e) {
                submitted = true;
            };
            this.picker.fire("save", {value: "foobar"});
            Assert.isTrue(submitted);
            var input = this.form.one("input");
            Assert.isInstanceOf(Y.Node, input);
            Assert.areSame("hidden", input.get("type"));
            Assert.areSame("field.changed_by", input.get("name"));
            Assert.areSame("foobar", input.get("value"));
        }

    };

    suite.add(new Y.Test.Case(TestLastChangedPicker));

    namespace.suite = suite;

}, "0.1", {"requires": [
               "lp.registry.distroseries.differences", "node",
               "node-event-simulate", "test", "test-console"]});
