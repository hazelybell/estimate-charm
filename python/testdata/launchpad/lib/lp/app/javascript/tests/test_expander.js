/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 */
YUI.add('lp.expander.test', function (Y) {
    var module = Y.lp.app.widgets.expander;

    function FakeAnim(config) {
        FakeAnim.superclass.constructor.apply(this, arguments);
        this.call_stack = [];
   }

    FakeAnim.ATTRS = {
        running: { value: false },
        reverse: { value: false },
        to: { value: {} },
        from: { value: {} }
    };

    Y.extend(FakeAnim, Y.Base, {
        stop: function() {
            this.call_stack.push('stop');
            this.set('running', false);
        },

        run: function() {
            this.call_stack.push('run');
            this.set('running', true);
        }
    });

    var tests = Y.namespace('lp.expander.test');
    tests.suite = new Y.Test.Suite('expander widget Tests');

    var ExpanderTestMixin = {

        setUp: function() {
            this.findTestHookTag().setContent('');
        },

        tearDown: function() {
            if (this.expander !== undefined) {
                this.expander.destroy();
            }
        },

        findTestHookTag: function() {
            return Y.one('.test-hook');
        },

        makeNode: function(css_class) {
            var node = Y.Node.create('<div></div>');
            if (css_class !== undefined) {
                node.addClass(css_class);
            }
            return node;
        },

        makeExpanderHooks: function(args) {
            if (!Y.Lang.isValue(args)) {
                args = {};
            }
            var root = this.makeNode();
            var hook = root.appendChild(this.makeNode('hook'));
            var icon = hook.appendChild(this.makeNode('icon'));
            var content = hook.appendChild(this.makeNode('content'));
            if (args.expanded) {
                content.addClass('expanded');
            }
            return root;
        },

        makeExpander: function(root, args) {
            if (!Y.Lang.isValue(args)) {
                args = {};
            }
            if (root === undefined) {
                root = this.makeExpanderHooks();
            }
            var expander = new module.Expander(
                root.one('.icon'), root.one('.content'), args.config);

            if (args.suppress_setup !== true) {
                expander.setUp();
            }
            this.expander = expander;
            return expander;
        }
    };

    tests.suite.add(new Y.Test.Case(
        Y.merge(ExpanderTestMixin, {

        name: 'expandable',

        test_separate_animate_node: function() {
            var icon = Y.Node.create('<td></td>'),
                content = Y.Node.create('<td></td>'),
                animate = Y.Node.create('<div></div>');
            var expander = new module.Expander(icon, content,
                                               { animate_node: animate });
            Y.Assert.areSame(content, expander.content_node);
            Y.Assert.areSame(animate, expander._animation.get('node'));
        },

        test_no_animate_node: function() {
            // When config.no_animation is true, no animation
            // is constructed or used.
            var expander = this.makeExpander(
                undefined, { config: { no_animation: true } });
            Y.Assert.isUndefined(expander._animation);
        },

        test_loaded_is_true_if_no_loader_is_defined: function() {
            var icon = Y.Node.create('<p></p>'),
                content = Y.Node.create('<p></p>');
            var expander = new module.Expander(icon, content);
            Y.Assert.isTrue(expander.loaded);
        },

        test_loaded_is_false_if_loader_is_defined: function() {
            var icon = Y.Node.create('<p></p>'),
                content = Y.Node.create('<p></p>');
            var config = {loader: function() {}};
            var expander = new module.Expander(icon, content, config);
            Y.Assert.isFalse(expander.loaded);
        },

        test_setUp_preserves_icon_content: function() {
            var root = this.makeExpanderHooks();
            root.one('.icon').set('text', "Click here");
            var icon = this.makeExpander(root).icon_node;
            Y.Assert.areEqual("Click here", icon.get('text'));
        },

        test_setUp_creates_collapsed_icon_by_default: function() {
            var icon = this.makeExpander().icon_node;
            Y.Assert.isTrue(icon.hasClass('sprite'));
            Y.Assert.isFalse(icon.hasClass('treeExpanded'));
            Y.Assert.isTrue(icon.hasClass('treeCollapsed'));
        },

        test_setUp_reveals_icon: function() {
            var root = this.makeExpanderHooks();
            var icon = root.one('.icon');
            icon.addClass('hidden');
            var expander = this.makeExpander(root);
            Y.Assert.isFalse(icon.hasClass('hidden'));
        },

        test_setUp_hides_content_by_default: function() {
            var content = this.makeExpander().content_node;
            Y.Assert.isTrue(content.hasClass('hidden'));
        },

        test_setUp_creates_expanded_icon_if_content_is_expanded: function() {
            var root = this.makeExpanderHooks({expanded: true});
            var icon = this.makeExpander(root).icon_node;
            Y.Assert.isTrue(icon.hasClass('treeExpanded'));
            Y.Assert.isFalse(icon.hasClass('treeCollapsed'));
        },

        test_setUp_reveals_content_if_content_is_expanded: function() {
            var root = this.makeExpanderHooks({expanded: true});
            var content = this.makeExpander(root).content_node;
            Y.Assert.isFalse(content.hasClass('hidden'));
        },

        test_setUp_does_not_run_loader_by_default: function() {
            var loader_has_run = false;
            var loader = function() {
                loader_has_run = true;
            };
            this.makeExpander(
                this.makeExpanderHooks(), {config: {loader: loader}});
            Y.Assert.isFalse(loader_has_run);
        },

        test_setUp_runs_loader_if_content_is_expanded: function() {
            var loader_has_run = false;
            var loader = function() {
                loader_has_run = true;
            };
            this.makeExpander(
                this.makeExpanderHooks({expanded: true}),
                {config: {loader: loader}});
            Y.Assert.isTrue(loader_has_run);
        },

        test_setUp_installs_click_handler: function() {
            var expander = this.makeExpander();
            var render_has_run = false;
            var fake_render = function() {
                render_has_run = true;
            };
            expander.render = fake_render;
            expander.icon_node.simulate('click');
            Y.Assert.isTrue(render_has_run);
        },

        test_setUp_linkifies_when_asked: function() {
            var wrap_has_run = false;
            var fake_wrapNodeWithLink = function() {
                wrap_has_run = true;
            };

            root = this.makeExpanderHooks();
            var expander = new module.Expander(
                root.one('.icon'), root.one('.content'));
            expander.wrapNodeWithLink = fake_wrapNodeWithLink;

            expander.setUp(true);
            Y.Assert.isTrue(wrap_has_run);
        },

        test_setUp_calls_foldContentNode_no_anim: function() {
            var foldContentNode_animate_arg = false;
            var fake_foldContentNode = function(expanded, no_animate) {
                foldContentNode_animate_arg = no_animate;
            };
            var expander = this.makeExpander(
                undefined, { supress_setup: true });
            expander.foldContentNode = fake_foldContentNode;
            expander.setUp();
            Y.Assert.isTrue(foldContentNode_animate_arg);
        },

        test_createByCSS_creates_expander: function() {
            var root = this.makeExpanderHooks();
            this.findTestHookTag().appendChild(root);
            module.createByCSS('.hook', '.icon', '.content');
            Y.Assert.isTrue(root.one('.content').hasClass('hidden'));
        },

        test_toggle_retains_content: function() {
            var root = this.makeExpanderHooks();
            root.one('.content').set('text', "Contents here");
            var expander = this.makeExpander(root);
            root.one('.icon').simulate('click');
            root.one('.icon').simulate('click');
            Y.Assert.areEqual(
                "Contents here", expander.content_node.get('text'));
        },

        test_loader_runs_only_once: function() {
            var loader_runs = 0;
            var loader = function() {
                loader_runs++;
            };
            var expander = this.makeExpander(
                this.makeExpanderHooks(), {config: {loader: loader}});
            expander.icon_node.simulate('click');
            expander.icon_node.simulate('click');
            expander.icon_node.simulate('click');
            Y.Assert.areEqual(1, loader_runs);
        },

        test_receive_replaces_contents: function() {
            var expander = this.makeExpander();
            var ajax_result = this.makeNode("ajax-result");
            expander.receive(ajax_result);
            Y.Assert.isTrue(expander.content_node.hasChildNodes());
            var children = expander.content_node.get('children');
            Y.Assert.areEqual(1, children.size());
            Y.Assert.areEqual(ajax_result, children.item(0));
        },

        test_receive_success_leaves_loaded: function() {
            var expander = this.makeExpander();
            Y.Assert.isTrue(expander.loaded);
            expander.receive('');
            Y.Assert.isTrue(expander.loaded);
        },

        test_receive_failure_resets_loaded: function() {
            var expander = this.makeExpander();
            Y.Assert.isTrue(expander.loaded);
            expander.receive('', true);
            Y.Assert.isFalse(expander.loaded);
        },

        test_receive_stops_and_restarts_animation: function() {
            var expander = this.makeExpander();
            var anim = new FakeAnim();
            anim.set('running', true);
            expander._animation = anim;
            expander.receive('');
            // Animation is first stopped, then restarted with run().
            Y.ArrayAssert.itemsAreSame(
                ['stop', 'run'], anim.call_stack);
        },

        test_receive_restarts_at_current_height: function() {
            var expander = this.makeExpander();

            var anim = new FakeAnim();
            expander._animation = anim;

            // We've got a half (well, 40%) open container node
            // with current height at 2px.
            var content_node = Y.Node.create('<div />')
                .setStyle('height', '2px');
            this.findTestHookTag().appendChild(content_node);
            expander.content_node = expander._animate_node = content_node;

            // Full desired content height of 5px.
            var content = Y.Node.create('<div />')
                .setStyle('height', '5px');

            expander.receive(content);
            // We get an integer from scrollHeight, and pixels from height.
            Y.Assert.areEqual(5, anim.get('to').height);
            Y.Assert.areEqual('2px', anim.get('from').height);
        },

        test_foldContentNode_expand_no_animation: function() {
            var expander = this.makeExpander();

            var anim = new FakeAnim();
            expander._animation = anim;

            // First parameter is true for expand, false for folding.
            // Second parameter indicates if no animation should be used
            // (true for no animation, anything else otherwise).
            expander.foldContentNode(true, true);

            // No anim.run() calls have been executed.
            Y.ArrayAssert.itemsAreEqual([], anim.call_stack);
            // And hidden CSS class has been removed.
            Y.Assert.isFalse(
                expander.content_node.hasClass("hidden"));
        },

        test_foldContentNode_fold_no_animation: function() {
            var expander = this.makeExpander();

            var anim = new FakeAnim();
            expander._animation = anim;

            // First parameter is true for expand, false for folding.
            // Second parameter indicates if no animation should be used
            // (true for no animation, anything else otherwise).
            expander.foldContentNode(false, true);

            // No anim.run() calls have been executed.
            Y.ArrayAssert.itemsAreEqual([], anim.call_stack);
            // And hidden CSS class has been added.
            Y.Assert.isTrue(
                expander.content_node.hasClass("hidden"));
        },

        test_foldContentNode_expand: function() {
            // Expanding a content node sets the animation direction
            // as appropriate ('reverse' to false) and removes the
            // 'hidden' CSS class.
            var expander = this.makeExpander();

            var anim = new FakeAnim();
            anim.set('reverse', true);
            expander._animation = anim;

            expander.foldContentNode(true);

            // Reverse flag has been toggled.
            Y.Assert.isFalse(anim.get('reverse'));
            // 'hidden' CSS class has been removed.
            Y.Assert.isFalse(expander.content_node.hasClass("hidden"));
            // Animation is shown.
            Y.ArrayAssert.itemsAreEqual(['run'], anim.call_stack);
        },

        test_foldContentNode_fold: function() {
            // Folding a content node sets the animation direction
            // as appropriate ('reverse' to false) and removes the
            // 'hidden' CSS class.
            var expander = this.makeExpander();

            var anim = new FakeAnim();
            anim.set('reverse', true);
            expander._animation = anim;
            // Initially expanded (with no animation).
            expander.foldContentNode(true, true);

            // Now fold it back.
            expander.foldContentNode(false);

            // Reverse flag has been toggled.
            Y.Assert.isTrue(anim.get('reverse'));
            // Animation is shown.
            Y.ArrayAssert.itemsAreEqual(['run'], anim.call_stack);
            // 'hidden' CSS class is added back, but only when
            // the animation completes.
            Y.Assert.isFalse(expander.content_node.hasClass("hidden"));
            anim.fire('end');
            Y.Assert.isTrue(expander.content_node.hasClass("hidden"));
        },

        test_foldContentNode_fold_expand: function() {
            // Quickly folding then re-expanding a node doesn't
            // set the 'hidden' flag.
            var expander = this.makeExpander();
            var anim = new FakeAnim();
            anim.set('reverse', true);
            expander._animation = anim;
            // Initially expanded (with no animation).
            expander.foldContentNode(true, true);

            // Now fold it.
            expander.foldContentNode(false);
            Y.Assert.isFalse(expander.content_node.hasClass("hidden"));
            // And expand it before animation was completed.
            expander.foldContentNode(true);
            // When animation for folding completes, it does not
            // set the 'hidden' CSS class because expanding is now
            // in progress instead.
            anim.fire('end');
            Y.Assert.isFalse(expander.content_node.hasClass("hidden"));
        },

        test_wrapNodeWithLink: function() {
            // Wraps node content with an <a href="#" class="js-action"> tag.
            var node = Y.Node.create('<div></div>')
                .set('text', 'Test');
            var expander = this.makeExpander();
            expander.wrapNodeWithLink(node);
            var link_node = node.one('a');
            Y.Assert.isNotNull(link_node);
            Y.Assert.areSame('Test', link_node.get('text'));
            Y.Assert.isTrue(link_node.hasClass('js-action'));
            // Link href is '#', but we get full test path appended
            // so instead we just ensure we've got a string back.
            Y.Assert.isString(link_node.get('href'));
        }
    })));

    tests.suite.add(new Y.Test.Case(
        Y.merge(ExpanderTestMixin, {

        name: 'ExpanderRadioController',

        test_no_expand_event_unless_group_defined: function() {
            // The expand event doesn't fire when there's no group.
            var event_fired = false;
            var root = this.makeExpanderHooks({expanded: true});
            var expander = this.makeExpander(root);
            Y.on(module.EXPANDER_STATE_CHANGED, function() {
                event_fired = true;
            });
            expander.icon_node.simulate('click');
            Y.Assert.isFalse(event_fired);
        },

        test_create_event_fired: function() {
            // The create event fires when the expander is instantiated.
            var event_fired = false;
            var root = this.makeExpanderHooks();
            var created_expander;
            var process_create =
                function(group_id, active_expander) {
                    Y.Assert.areEqual('group id', group_id);
                    created_expander = active_expander;
                    event_fired = true;
                };
            Y.on(module.EXPANDER_CREATED, process_create);
            var expander = this.makeExpander(
                root, { config: { group_id: 'group id' } });
            Y.detach(module.EXPANDER_CREATED, process_create);
            Y.Assert.isTrue(event_fired);
            Y.Assert.areEqual(created_expander, expander);
        },

        test_destroy_event_fired: function() {
            // The destroy event fires when the expander is destroyed.
            var event_fired = false;
            var root = this.makeExpanderHooks();
            var expander = this.makeExpander(
                root, { config: { group_id: 'group id' } });
            var process_destroy =
                function(group_id, active_expander) {
                    Y.Assert.areEqual('group id', group_id);
                    Y.Assert.areEqual(expander, active_expander);
                    event_fired = true;
                };
            Y.on(module.EXPANDER_DESTORYED, process_destroy);
            expander.destroy();
            Y.detach(module.EXPANDER_DESTORYED, process_destroy);
            Y.Assert.isTrue(event_fired);
        },

        test_expand_event_fired: function() {
            // The expand event fires when the expander opens.
            var event_fired = false;
            var root = this.makeExpanderHooks({expanded: false});
            var expander = this.makeExpander(
                root, { config: { group_id: 'group id' } });
            var process_state_changed =
                function(group_id, new_state, active_expander) {
                    Y.Assert.areEqual('group id', group_id);
                    Y.Assert.areEqual(module.EXPANDED, new_state);
                    Y.Assert.areEqual(expander, active_expander);
                    event_fired = true;
                };
            Y.on(module.EXPANDER_STATE_CHANGED, process_state_changed);
            expander.icon_node.simulate('click');
            Y.detach(module.EXPANDER_STATE_CHANGED, process_state_changed);
            Y.Assert.isTrue(event_fired);
        },

        test_collapse_event_fired: function() {
            // The collapse event fires when the expander closes.
            var event_fired = false;
            var root = this.makeExpanderHooks({expanded: true});
            var expander = this.makeExpander(
                root, { config: { group_id: 'group id' } });
            var process_state_changed =
                function(group_id, new_state, active_expander) {
                    Y.Assert.areEqual('group id', group_id);
                    Y.Assert.areEqual(module.COLLAPSED, new_state);
                    Y.Assert.areEqual(expander, active_expander);
                    event_fired = true;
                };
            Y.on(module.EXPANDER_STATE_CHANGED, process_state_changed);
            expander.icon_node.simulate('click');
            Y.detach(module.EXPANDER_STATE_CHANGED, process_state_changed);
            Y.Assert.isTrue(event_fired);
        },

        _makeAnotherExpander: function(expanded, group_id) {
            var root = this.makeExpanderHooks({expanded: expanded});
            var expander = new module.Expander(
                root.one('.icon'),
                root.one('.content'),
                { group_id: group_id });
            expander.setUp();
            return expander;
        },

        test_only_one_open: function() {
            // If an expander is opened, all other open expanders in the
            // same group should be closed.
            var expander1 = this._makeAnotherExpander(true, "group1");
            var expander2 = this._makeAnotherExpander(false, "group1");
            var expander3 = this._makeAnotherExpander(false, "group1");
            expander2.icon_node.simulate('click');
            Y.Assert.isFalse(expander1.isExpanded());
            Y.Assert.isTrue(expander2.isExpanded());
            Y.Assert.isFalse(expander3.isExpanded());
        },

        test_other_groups_left_alone: function() {
            // Only the expanders in the same group as the one that changed
            // state should be processed.
            var expander1 = this._makeAnotherExpander(true, "group1");
            var expander2 = this._makeAnotherExpander(false, "group1");
            var expander3 = this._makeAnotherExpander(true, "group2");
            var expander4 = this._makeAnotherExpander(true);
            expander2.icon_node.simulate('click');
            Y.Assert.isFalse(expander1.isExpanded());
            Y.Assert.isTrue(expander2.isExpanded());
            Y.Assert.isTrue(expander3.isExpanded());
            Y.Assert.isTrue(expander4.isExpanded());
        }
    })));


}, '0.1', {
    requires: ['lp.testing.runner', 'base', 'test', 'test-console', 'node',
               'node-event-simulate', 'lp.app.widgets.expander']
});
