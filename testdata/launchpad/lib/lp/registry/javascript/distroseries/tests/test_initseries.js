/**
 * Copyright 2011 Canonical Ltd. This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Tests for DistroSeries Initialization.
 *
 * @module lp.registry.distroseries.initseries
 * @submodule test
 */

YUI.add('lp.registry.distroseries.initseries.test', function(Y) {

    var namespace = Y.namespace('lp.registry.distroseries.initseries.test');

    var Assert = Y.Assert,
        ArrayAssert = Y.ArrayAssert,
        attrselect = Y.lp.extras.attrselect;

    var suite = new Y.Test.Suite("distroseries.initseries Tests");
    var initseries = Y.lp.registry.distroseries.initseries;
    var widgets = Y.lp.registry.distroseries.widgets;

    var testDeriveDistroSeriesActionsWidget = {
        name: 'TestDeriveDistroSeriesActionsWidget',

        setUp: function() {
            this.actions = this.makeActionsDiv();
            this.widget = new initseries.DeriveDistroSeriesActionsWidget({
                duration: 0,
                srcNode: this.actions,
                context: {
                    name: "hagfish",
                    displayname: "Horrid Hagfish",
                    self_link: "http://ex.com/api/devel/deribuntu/snaggle"
                },
                deriveFromChoices: {
                    get: function(name) {
                        if (name === "parents") {
                            return ["4", "5"];
                        }
                        else if (name === "overlays") {
                            return [true, false];
                        }
                        else if (name === "overlay_pockets") {
                            return ['Updates', null];
                        }
                        else if (name === "overlay_components") {
                            return ['restricted', null];
                        }
                        else {
                            Assert.fail("Unrecognized property: " + name);
                            return null; // Keep lint quiet.
                        }
                    }
                },
                architectureChoice: {
                    get: function(name) {
                        Assert.areEqual("choice", name);
                        return [
                            {value: "i386", text: "i386"},
                            {value: "sparc", text: "sparc"}
                        ];
                    }
                },
                architectureIndepChoice: {
                    AUTOSELECT: '-',
                    get: function(name) {
                        Assert.areEqual("choice", name);
                        return {value: "sparc", text: "sparc"};
                    }
                },
                packagesetChoice: {
                    get: function(name) {
                        Assert.areEqual("choice", name);
                        return [
                            {value: "4", text: "FooSet"},
                            {value: "5", text: "BarSet"}
                        ];
                    }
                },
                packageCopyOptions: {
                    get: function(name) {
                        Assert.areEqual("choice", name);
                        return {
                            value: "rebuild",
                            text: "Copy Source and Rebuild"
                        };
                    }
                }
            });
            this.form = Y.Node.create("<form />");
            this.form.append(this.actions);
            this.container = Y.Node.create("<div />");
            this.container.append(this.form);
            this.body = Y.one("body");
            this.body.append(this.container);
        },

        tearDown: function() {
            this.container.remove(true);
        },

        testSuccess: function() {
            Assert.isTrue(this.container.contains(this.form));
            Assert.isNull(this.body.one("p.informational.message"));
            this.widget.success();
            Assert.areEqual(
                ("The initialization of Horrid Hagfish " +
                 "has been scheduled and should run shortly."),
                this.body.one("p.informational.message").get("text"));
            // The form is slowly evaporated.
            this.wait(function() {
                Assert.isFalse(
                    this.container.contains(this.form));
            }, 90);
        },

        testSubmit: function() {
            var io = false;
            this.widget.client = {
                named_post: function(path, operation, config) {
                    io = true;
                    Assert.areEqual(
                        "http://ex.com/api/devel/deribuntu/snaggle",
                        path);
                    Assert.areEqual("initDerivedDistroSeries", operation);
                    ArrayAssert.itemsAreEqual(
                        ["4", "5"],
                        config.parameters.parents);
                    ArrayAssert.itemsAreEqual(
                        [true, false],
                        config.parameters.overlays);
                    ArrayAssert.itemsAreEqual(
                        ['Updates', null],
                        config.parameters.overlay_pockets);
                    ArrayAssert.itemsAreEqual(
                        ['restricted', null],
                        config.parameters.overlay_components);
                    ArrayAssert.itemsAreEqual(
                        ["i386", "sparc"],
                        config.parameters.architectures);
                    ArrayAssert.itemsAreEqual(
                        "sparc",
                        config.parameters.archindep_archtag);
                    ArrayAssert.itemsAreEqual(
                        ["4", "5"],
                        config.parameters.packagesets);
                    Assert.isTrue(config.parameters.rebuild);
                    Assert.isObject(config.on);
                    Assert.isFunction(config.on.success);
                    Assert.isFunction(config.on.failure);
                }
            };
            this.widget.submit();
            Assert.isTrue(io, "No IO initiated.");
        }

    };

    testDeriveDistroSeriesActionsWidget = Y.merge(
        Y.lp.app.formwidgets.test.testFormActionsWidget,
        testDeriveDistroSeriesActionsWidget);
    suite.add(new Y.Test.Case(testDeriveDistroSeriesActionsWidget));


    var init_form = Y.one('#init-form').getContent();

    var testDeriveDistroSeriesSetup = {
        name: 'TestDeriveDistroSeriesSetup',

        setUp: function() {
           var node = Y.Node.create(init_form);
           Y.one('body').appendChild(node);
        },

        setUpArches: function(arch_choices, archindep_tags) {
            var cache = {is_first_derivation: true};
            this.form_actions = initseries.setupWidgets(cache);
            this.form_actions.architectureChoice.set(
                'choices', arch_choices);
            this.form_actions.architectureChoice._archindep_tags =
                archindep_tags;
            this.form_actions.architectureIndepChoice.add_choices(
                arch_choices);
        },

        assertShowsError: function(field, expected_error_msg) {
            var error_msg = field.get(
                'contentBox').one('.message').get('text');
            Assert.areEqual(expected_error_msg, error_msg);
        },

        testValidateNoArchIndepChoiceOk: function() {
            this.setUpArches(['i386', 'hppa'], {'3': 'i386'});
            this.form_actions.architectureChoice.set(
                'choice', 'i386');
            this.form_actions.architectureIndepChoice.set(
                'choice', 'i386');
            Assert.isTrue(this.form_actions.validate());
        },

        testValidateNoArchIndepChoiceFailNotAmong: function() {
            // Validation fails if the selected arch indep architecture
            // is not among the selected architectures for the derived series.
            this.setUpArches(['i386', 'hppa'], {'3': 'i386'});
            this.form_actions.architectureChoice.set(
                'choice', 'i386');
            this.form_actions.architectureIndepChoice.set(
                'choice', 'hppa');
            Assert.isFalse(this.form_actions.validate());
            this.assertShowsError(
                this.form_actions.architectureIndepChoice,
                'The selected architecture independent builder is not ' +
                'among the selected architectures.');
        },

        testValidateAutoArchIndepOk: function() {
            this.setUpArches(['i386', 'hppa'], {'3': 'i386'});
            this.form_actions.architectureChoice.set(
                'choice', 'i386');
            this.form_actions.architectureIndepChoice.set(
                'choice',
                this.form_actions.architectureIndepChoice.AUTOSELECT);
            Assert.isTrue(this.form_actions.validate());
        },

        testValidateAutoArchIndepOkAll: function() {
            // If no architecture is selected, it means that all the
            // architectures from the parents will be copied over.
            this.setUpArches(['i386', 'hppa'], {'3': 'i386'});
            this.form_actions.architectureIndepChoice.set(
                'choice',
                this.form_actions.architectureIndepChoice.AUTOSELECT);
            Assert.isTrue(this.form_actions.validate());
        },

        testValidateAutoArchIndepChoiceFail: function() {
            // Validation fails if the arch indep architecture is not
            // specified and none of the parents' arch indep architectures
            // has been selected.
            this.setUpArches(['i386', 'hppa'], {'3': 'i386'});
            this.form_actions.architectureChoice.set(
                'choice', 'hppa');
            this.form_actions.architectureIndepChoice.set(
                'choice',
                this.form_actions.architectureIndepChoice.AUTOSELECT);
            Assert.isFalse(this.form_actions.validate());
            this.assertShowsError(
                this.form_actions.architectureChoice,
                'The distroseries has no architectures selected to build ' +
                'architecture independent binaries.');
            this.assertShowsError(
                this.form_actions.architectureIndepChoice,
                'Alternatively, you can specify the architecture ' +
                'independent builder.');
        },

        testIsFirstDerivation: function() {
            var cache = {is_first_derivation: true};
            var form_actions = initseries.setupWidgets(cache);
            initseries.setupInteraction(form_actions, cache);

            // No pre-populated parent.
            ArrayAssert.itemsAreEqual(
                [],
                form_actions.deriveFromChoices.get("parents"));
        },

        testDefaultRebuildChoice: function() {
            var cache = {is_first_derivation: true};
            var form_actions = initseries.setupWidgets(cache);
            Assert.areEqual(
                "copy",
                form_actions.packageCopyOptions.get('choice').value);
        },

        getFakeClient: function(res_sequence, return_obj) {
            var count = 0;
            var client = {
                get: function(path, config) {
                    Assert.areEqual(path, res_sequence[count][0]);
                    var return_obj = res_sequence[count][1];
                    count = count + 1;
                    if (return_obj instanceof Array) {
                        return_obj = new Y.lp.client.Collection(
                            null, {entries: return_obj}, null);
                    }
                    config.on.success(return_obj);
                }
            };
            return client;
        },

        testIsNotFirstDerivation: function() {
            var cache = {
                is_first_derivation: false,
                previous_series: {
                    api_uri: '/ubuntu/natty',
                    value: '3',
                    title: 'Ubunty: Natty'
                },
                previous_parents: [
                    {api_uri: '/debian/sid',
                     value: '4', title: 'Debian: Sid'},
                    {api_uri: '/zz/aa',
                     value: '5', title: 'ZZ: aa'}
                ]
            };
            var form_actions = initseries.setupWidgets(cache);
            // Monkeypatch LP client.
            var mockNominatedArchIndep = Y.Mock();
            Y.Mock.expect(mockNominatedArchIndep, {
                method: "get",
                args: ["architecture_tag"],
                returns: "i386"
            });
            var client = this.getFakeClient(
                [["/ubuntu/natty/architectures",
                  [{'architecture_tag': 'hppa'},
                   {'architecture_tag': 'i386'}]],
                 ["/api/devel/ubuntu/natty/nominatedarchindep",
                  mockNominatedArchIndep]]
                );
            form_actions.architectureChoice.client = client;
            initseries.setupInteraction(form_actions, cache);

            // Parents are populated.
            ArrayAssert.itemsAreEqual(
                ['4', '5'],
                form_actions.deriveFromChoices.get("parents"));
            // No packageset choice widget.
            Assert.isNull(form_actions.packagesetChoice);
            // The architecture picker features the architectures
            // from the previous series.
            ArrayAssert.itemsAreEqual(
                ['hppa', 'i386'],
                attrselect("value")(
                    form_actions.architectureChoice.get("choices")));
            Y.Mock.verify(mockNominatedArchIndep);
         }
    };

    suite.add(new Y.Test.Case(testDeriveDistroSeriesSetup));
    namespace.suite = suite;

}, "0.1", {"requires": [
               'test', 'test-console', 'node-event-simulate',
               'lp.app.formwidgets.test', 'lp.extras',
               'lp.registry.distroseries.initseries']});
