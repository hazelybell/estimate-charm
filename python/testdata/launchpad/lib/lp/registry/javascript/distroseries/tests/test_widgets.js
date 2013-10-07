/**
 * Copyright 2011 Canonical Ltd. This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Tests for DistroSeries Widgets.
 *
 * @module lp.registry.distroseries.widgets
 * @submodule test
 */

YUI.add('lp.registry.distroseries.widgets.test', function(Y) {

    var namespace = Y.namespace('lp.registry.distroseries.widgets.test');

    var Assert = Y.Assert;
    var ArrayAssert = Y.ArrayAssert;

    var suite = new Y.Test.Suite("distroseries.widgets Tests");
    var widgets = Y.lp.registry.distroseries.widgets;
    var formwidgets = Y.lp.app.formwidgets;

    var attrselect = Y.lp.extras.attrselect;

    var testParentSeriesListWidget = {
        name: 'TestParentSeriesListWidget',

        setUp: function() {
            this.container = Y.Node.create("<div />");
            this.widget = new widgets.ParentSeriesListWidget();
        },

        tearDown: function() {
            this.container.remove(true);
        },

        testIsClean: function() {
            Assert.areEqual(
                "[No parent for this series yet!]",
                this.widget.fieldNode.one("div").get("text"));
        },

        testBuildSelector: function() {
            var node = Y.Node.create(
                '<tr id="snarf">' +
                '<td><input type="checkbox"/></td>' +
                '<td class="test"></td>' +
                '</tr>');
            Y.one('body').append(node);
            node = Y.one('#snarf');
            this.widget.build_selector(node, ['a', 'b', 'c'], 'test');
            Assert.areEqual(
                '<td><input type="checkbox"></td>' +
                '<td class="test">' +
                '<select disabled="disabled">' +
                '<option value="a">a</option>' +
                '<option value="b">b</option>' +
                '<option value="c">c</option>' +
                '</select>' +
                '</td>', node.get('innerHTML'));
            Y.one('body').removeChild(node);
        },

        testAddParentAddsLine: function() {
            var parent;
            parent = {value: "4", title: "Hoary", api_uri: "ubuntu/hoary"};
            Assert.areEqual(
                0,
                this.widget.fieldNode.all('tr.parent').size());
            this.widget.add_parent(parent);
            Assert.areEqual(
                1,
                this.widget.fieldNode.all('tr.parent').size());
            var new_line = this.widget.fieldNode.one('tr.parent');
            Assert.areEqual(
                'parent-4',
                new_line.get('id'));
        },

        testAddDuplicateParent: function() {
            var parent;
            parent = {value: "4", title: "Hoary", api_uri: "ubuntu/hoary"};
            Assert.isTrue(
                this.widget.add_parent(parent),
                "Parent not added.");
            this.widget.add_parent(parent);
            Assert.isFalse(
                this.widget.add_parent(parent),
                "Parent added twice.");
            Assert.areEqual(
                1,
                this.widget.fieldNode.all('tr.parent').size());
        },

        testParentOrdering: function() {
            var parent;
            parent = {value: "4", title: "Hoary", api_uri: "ubuntu/hoary"};
            this.widget.add_parent(parent);
            parent = {value: "3", title: "Warty", api_uri: "ubuntu/warty"};
            this.widget.add_parent(parent);
            Assert.areEqual(
                'parent-4',
                this.widget.fieldNode.one('tr.parent').get('id'));
            // Move first parent down.
            this.widget.fieldNode.one(
                'tr#parent-4').one('a.move-down').simulate("click");
            Assert.areEqual(
                'parent-3',
                this.widget.fieldNode.one('tr.parent').get('id'));
            // Move second parent up.
            this.widget.fieldNode.one(
                'tr#parent-4').one('a.move-up').simulate("click");
            Assert.areEqual(
                'parent-4',
                this.widget.fieldNode.one('tr.parent').get('id'));
        },

        testRemoveParent: function() {
            var parent;
            parent = {value: "4", title: "Hoary", api_uri: "ubuntu/hoary"};
            this.widget.add_parent(parent);
            parent = {value: "3", title: "Warty", api_uri: "ubuntu/warty"};
            this.widget.add_parent(parent);
            Assert.areEqual(
                2,
                this.widget.fieldNode.all('tr.parent').size());
            // Delete first parent.
            this.widget.fieldNode.one(
                'tr#parent-4').one('span.remove').simulate("click");
            Assert.areEqual(
                1,
                this.widget.fieldNode.all('tr.parent').size());
            Assert.areEqual(
                'parent-3',
                this.widget.fieldNode.one('tr.parent').get('id'));
            // Delete second parent.
            this.widget.fieldNode.one(
                'tr#parent-3').one('span.remove').simulate("click");
            Assert.areEqual(
                0,
                this.widget.fieldNode.all('tr.parent').size());
            // The parent table is empty.
            Assert.areEqual(
                "[No parent for this series yet!]",
                this.widget.fieldNode.one("div").get("text"));
        },

        testParentGetter: function() {
            var parent;
            parent = {value: "4", title: "Hoary", api_uri: "ubuntu/hoary"};
            this.widget.add_parent(parent);
            parent = {value: "3", title: "Warty", api_uri: "ubuntu/warty"};
            this.widget.add_parent(parent);
            ArrayAssert.itemsAreEqual(
                ["4", "3"],
                this.widget.get('parents'));
        }

    };

    testParentSeriesListWidget = Y.merge(
        formwidgets.test.testFormRowWidget, testParentSeriesListWidget);
    suite.add(new Y.Test.Case(testParentSeriesListWidget));

   var testArchitecturesChoiceListWidget = {
        name: 'TestArchitecturesChoiceListWidget',

        setUp: function() {
            this.container = Y.Node.create("<div />");
            this.widget = new widgets.ArchitecturesChoiceListWidget();
        },

        tearDown: function() {
            this.container.remove(true);
        },

        setupDistroArchSerieses: function(arches) {
            var distro_arch_serieses = [];
            var i;
            for (i=0; i<arches.length; i++) {
                distro_arch_serieses.push({architecture_tag: arches[i]});
            }
            var res = new Y.lp.client.Collection(
                null, {entries: distro_arch_serieses}, null);
            return res;
         },

        testAddDistroArchSerieses: function() {
           var collection = this.setupDistroArchSerieses(
               ["i386", "amd64", "i386"]);
           this.widget.add_distroarchseries(3, collection);
            ArrayAssert.itemsAreEqual(
                ["amd64", "i386"],
                attrselect("value")(this.widget.get("choices")));
        },

        testAddDistroArchSeriesesFiresEvent: function() {
            var collection = this.setupDistroArchSerieses(
                ["i386", "amd64", "i386"]);
            var event_fired = false;
            var handleEvent = function(e, arch_list) {
                event_fired = true;
                ArrayAssert.itemsAreEqual(
                    ["i386", "amd64", "i386"], arch_list);
            };
            this.widget.on(
                this.widget.name + ":added_choices",
                handleEvent, this.widget);
            this.widget.add_distroarchseries(3, collection);
            Assert.isTrue(event_fired);
        },

        test_populate_archindep_tags_InitiatesIO: function() {
            var distroseries = {api_uri: "ubuntu/hoary", value: 3};
            var io = false;
            this.widget.client = {
                get: function(path, config) {
                    io = true;
                    Assert.areEqual(
                        "/api/devel/ubuntu/hoary/nominatedarchindep",
                        path);
                    Assert.isObject(config.on);
                    Assert.isFunction(config.on.success);
                    Assert.isFunction(config.on.failure);
                }
            };
            this.widget._populate_archindep_tags(distroseries);
            Assert.isTrue(io, "No IO initiated.");
        },

        setup_widget_client: function() {
            this.widget.client = {
                get: function(path, config) {
                    var nominatedarchindep = {
                        get: function(key) {
                            Assert.areEqual("architecture_tag", key);
                            return 'i386';
                        }
                    };
                    config.on.success(nominatedarchindep);
                }
            };
         },

        test_populate_archindep_tags: function() {
            this.setup_widget_client();
            distroseries = {api_uri: "ubuntu/hoary", value: "3"};
            this.widget._populate_archindep_tags(distroseries);
            Assert.areEqual("i386", this.widget._archindep_tags["3"]);
        },

        test_validate_arch_indep_Ok: function() {
            this.widget.add_choices(['i386', 'hppa']);
            this.widget.set('choice', ['i386']);
            this.widget._archindep_tags['3'] = 'i386';
            var res = this.widget.validate_arch_indep();
            Assert.isTrue(res);
        },

        test_validate_arch_indep_Ok_empty: function() {
            this.widget.add_choices(['i386', 'hppa']);
            this.widget.set('choice', []);
            this.widget._archindep_tags['3'] = 'i386';
            var res = this.widget.validate_arch_indep();
            Assert.isTrue(res);
        },

        test_validate_arch_indep_Fails: function() {
            this.widget.add_choices(['i386', 'hppa']);
            this.widget.set('choice', ['i386']);
            this.widget._archindep_tags['3'] = 'hppa';
            var res = this.widget.validate_arch_indep();
            Assert.isFalse(res);
        },

        test_show_error_arch_indep: function() {
            this.widget.render(this.container);
            this.widget.show_error_arch_indep();
            Assert.areEqual(
                "The distroseries has no architectures selected to "
                + "build architecture independent binaries.",
                this.widget.fieldNode.one('.message').get('text'));
        },

        testAddDistroSeriesInitiatesIO: function() {
            var io = false;
            this.widget.client = {
                get: function(path, config) {
                    io = true;
                    Assert.areEqual("ubuntu/hoary/architectures", path);
                    Assert.isObject(config.on);
                    Assert.isFunction(config.on.success);
                    Assert.isFunction(config.on.failure);
                }
            };
            var distroseries = {api_uri: "ubuntu/hoary", value: 3};
            this.widget.add_distroseries(distroseries);
            Assert.isTrue(io, "No IO initiated.");
        },

        testRemoveDistroSeries: function() {
            var values = attrselect("value");
            var distro_arch_serieses1 = [
                {architecture_tag: "i386"},
                {architecture_tag: "amd64"},
                {architecture_tag: "i386"}
            ];
            var distro_arch_serieses_collection1 =
                new Y.lp.client.Collection(
                    null, {entries: distro_arch_serieses1}, null);
            this.widget.add_distroarchseries(
                "3",
                distro_arch_serieses_collection1);
            ArrayAssert.itemsAreEqual(
                ["amd64", "i386"],
                values(this.widget.get("choices")));
            var distro_arch_serieses2 = [
                {architecture_tag: "hppa"},
                {architecture_tag: "hppa"},
                {architecture_tag: "i386"}
            ];
            var distro_arch_serieses_collection2 =
                new Y.lp.client.Collection(
                    null, {entries: distro_arch_serieses2}, null);
            this.widget.add_distroarchseries(
                "4",
                distro_arch_serieses_collection2);
            ArrayAssert.itemsAreEqual(
                ["amd64", "hppa", "i386"],
                values(this.widget.get("choices")));
            this.widget.remove_distroseries("4");
            ArrayAssert.itemsAreEqual(
                ["amd64", "i386"],
                values(this.widget.get("choices")));
            Assert.isUndefined(this.widget._archindep_tags["4"]);
        },

        testRemoveDistroSeriesFiresEvent: function() {
            var collection = this.setupDistroArchSerieses(
                ["i386", "amd64", "i386"]);
            this.widget.add_distroarchseries(3, collection);
            var collection2 = this.setupDistroArchSerieses(
                ["i386", "amd64", "hppa"]);
            this.widget.add_distroarchseries(4, collection2);
            var event_fired = false;
            var handleEvent = function(e, arch_list) {
                event_fired = true;
                ArrayAssert.itemsAreEqual(["hppa"], arch_list);
            };
            this.widget.on(
                this.widget.name + ":removed_choices",
                handleEvent, this.widget);
            this.widget.remove_distroseries("4");
            Assert.isTrue(event_fired);
        },

        testSetDistroSeriesError: function() {
            var widget = this.widget;
            widget.client = {
                get: function(path, config) {
                    config.on.failure(
                        null, {status: 404,
                               responseText: "Not found"});
                    Assert.areEqual(
                        "Not found",
                        widget.fieldNode.one("p").get("text"));
                }
            };
            this.widget.set("distroSeries", "ubuntu/hoary");
        }

    };

    testArchitecturesChoiceListWidget = Y.merge(
        formwidgets.test.testChoiceListWidget,
        testArchitecturesChoiceListWidget);
    suite.add(new Y.Test.Case(testArchitecturesChoiceListWidget));


    var testArchIndepChoiceListWidget = {
        name: 'TestArchIndepChoiceListWidget',

        setUp: function() {
            this.container = Y.Node.create("<div />");
            this.widget = new widgets.ArchIndepChoiceListWidget();
        },

        tearDown: function() {
            this.container.remove(true);
        },

        testInitialized: function() {
            Assert.isFalse(this.widget.get('multiple'));
            ArrayAssert.itemsAreEqual(
                ["Auto select"],
                attrselect("text")(this.widget.get("choices")));
            ArrayAssert.itemsAreEqual(
                [this.widget.AUTOSELECT],
                attrselect("value")(this.widget.get("choices")));
            Assert.areEqual(
                this.widget.AUTOSELECT,
                attrselect("value")(this.widget.get('choice')));
        },

        test_default_select_called: function() {
            this.widget.add_choices(['4', '5']);
            this.widget.set('choice', '5');
            this.widget.remove_choices(['5']);
                Y.log(this.widget.get('choice'));
            Assert.areEqual(
                this.widget.AUTOSELECT,
                attrselect("value")(this.widget.get('choice')));
        }

    };

    suite.add(new Y.Test.Case(testArchIndepChoiceListWidget));


    var testPackagesetPickerWidget = {
        name: 'TestPackagesetPickerWidget',

        setUp: function() {
            this.container = Y.Node.create("<div />");
            this.widget = new widgets.PackagesetPickerWidget();
        },

        tearDown: function() {
            this.container.remove(true);
        },

        _getValues: function(items) {
            return items.map(
                function(item) {
                    return item.text;
                }
            );
        },

        testAddPackagesets: function() {
            var package_sets = [
                {id: "4", name: "foo", description: "Foo"},
                {id: "5", name: "bar", description: "Bar"},
                {id: "7", name: "baz", description: "Baz"}
            ];
            var package_sets_collection =
                new Y.lp.client.Collection(
                    null, {entries: package_sets}, null);
            var distroseries = {value: "4", title: "series1"};
            this.widget.add_packagesets(
                package_sets_collection, distroseries);
            var choices = this.widget.get("choices");
            ArrayAssert.itemsAreEqual(
                ["5", "7", "4"],
                attrselect("value")(choices));
        },

        testAddDistroSeriesInitiatesIO: function() {
            var io = false;
            this.widget.client = {
                named_get: function(path, operation, config) {
                    io = true;
                    Assert.areEqual("package-sets", path);
                    Assert.areEqual("getBySeries", operation);
                    Assert.isNotNull(
                        config.parameters.distroseries.match(
                            new RegExp("/ubuntu/hoary$")));
                    Assert.isObject(config.on);
                    Assert.isFunction(config.on.success);
                    Assert.isFunction(config.on.failure);
                }
            };
            var distroseries = {
                value: "4", title: "series1", api_uri: "ubuntu/hoary"};
            this.widget.add_distroseries(distroseries);
            Assert.isTrue(io, "No IO initiated.");
        },

        testAddDistroSeriesUpdatesPackageSets: function() {
            var package_sets = [
                {id: "4", name: "foo", description: "Foo"},
                {id: "5", name: "bar", description: "Bar"},
                {id: "6", name: "baz", description: "Baz"}
            ];
            var package_sets_collection =
                new Y.lp.client.Collection(
                    null, {entries: package_sets}, null);
            this.widget.client = {
                named_get: function(path, operation, config) {
                    config.on.success(package_sets_collection);
                }
            };
            var distroseries = {
                value: "4", title: "series1", api_uri: "ubuntu/hoary"};
            this.widget.add_distroseries(distroseries);
            ArrayAssert.itemsAreEqual(
                ["5", "6", "4"],
                attrselect("value")(this.widget.get("choices")));
        },

        testRemoveDistroSeriesUpdatesPackageSets: function() {
            // Calling remove_distroseries removes the packagesets
            // related to the distroseries from the widget.

            // Setup a first distroseries with a bunch of packagesets.
            var distroseries1 = {
                value: "1", title: "series1",
                api_uri: "ubuntu/hoary"};
            var package_sets1 = [
                {id: "4", name: "aa", description: "Aa"},
                {id: "5", name: "bb", description: "Bb"}
            ];
            var package_sets_collection1 =
                new Y.lp.client.Collection(
                    null, {entries: package_sets1}, null);

            // Setup a second distroseries with other packagesets.
            var distroseries2 = {
                value: "2", title: "series2",
                api_uri: "ubuntu/breezy"};
            var package_sets2 = [
                {id: "6", name: "cc", description: "Cc"},
                {id: "7", name: "dd", description: "Dd"}
            ];
            var package_sets_collection2 =
                new Y.lp.client.Collection(
                    null, {entries: package_sets2}, null);

            // Setup the client so that the proper packagesets are returned
            // for each distroseries.
            var package_set_collections = {
                'hoary': package_sets_collection1,
                'breezy': package_sets_collection2
            };
            this.widget.client = {
                named_get: function(path, operation, config) {
                    var series_name = config
                        .parameters.distroseries.split('/')[6];
                    config.on.success(package_set_collections[series_name]);
                }
            };

            // Add the two series.
            this.widget.add_distroseries(distroseries1);
            this.widget.add_distroseries(distroseries2);
            // The packagesets widget has been populated with the
            // packagesets from the series.
            ArrayAssert.itemsAreEqual(
                ["4", "5", "6", "7"],
                attrselect("value")(this.widget.get("choices")));

            // Remove a series.
            this.widget.remove_distroseries("2");
            // The remaining packagesets are those from the remaining series.
            ArrayAssert.itemsAreEqual(
                ["4", "5"],
                attrselect("value")(this.widget.get("choices")));
        }

    };

    testPackagesetPickerWidget = Y.merge(
        formwidgets.test.testChoiceListWidget,
        testPackagesetPickerWidget);
    suite.add(new Y.Test.Case(testPackagesetPickerWidget));


    // Exports.
    namespace.suite = suite;

}, "0.1", {"requires": [
               'test', 'test-console', 'node-event-simulate',
               'lp.registry.distroseries.widgets', 'lp.app.formwidgets',
               'lp.app.formwidgets.test', 'lp.extras']});
