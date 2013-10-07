YUI.add('lp.bug_tags_entry.test', function (Y) {
    var module = Y.lp.bugs.tags_entry;

    var tests = Y.namespace('lp.bug_tags_entry.test');
    tests.suite = new Y.Test.Suite('Bug tags entry Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'Tags parsing',

        test_empty_string: function() {
            var tag_string = '';
            var results = module.parse_tags(tag_string);
            Y.ArrayAssert.itemsAreEqual([], results);
        },

        test_one_item: function() {
            var tag_string = 'cow';
            var results = module.parse_tags(tag_string);
            Y.ArrayAssert.itemsAreEqual(['cow'], results);
        },

        test_two_items: function() {
            var tag_string = 'cow pig';
            var results = module.parse_tags(tag_string);
            Y.ArrayAssert.itemsAreEqual(['cow', 'pig'], results);
        },

        test_spaces: function() {
            var tag_string = '   ';
            var results = module.parse_tags(tag_string);
            Y.ArrayAssert.itemsAreEqual([], results);
        },

        test_items_with_spaces: function() {
            var tag_string = ' cow pig  chicken  ';
            var results = module.parse_tags(tag_string);
            Y.ArrayAssert.itemsAreEqual(['cow', 'pig', 'chicken'], results);
        }

      }));

    tests.suite.add(new Y.Test.Case({
        name: 'Actions',

        setUp: function() {
            this.fixture = Y.one("#fixture");
            var template = Y.one('#edit-bug-tag-form').getContent();
            this.fixture.append(template);
            this.bug_tags_div = Y.one('#bug-tags');
            window.LP = {
                links: {me : "/~user"},
                cache: {
                    bug: {
                        resource_type_link: 'Bug',
                        self_link: '/bug/1',
                        tags: ['project-tag']}
                    }
                };
        },

        tearDown: function() {
            if (this.fixture !== null) {
                this.fixture.empty();
            }
            delete this.fixture;
            delete window.LP;
        },

        _set_common_elements: function() {
            this.tags_heading = Y.one('#tags-heading');
            this.tags_trigger = Y.one('#tags-trigger');
            this.tag_list_span = Y.one('#tag-list');
            this.tags_form = Y.one('#tags-form');
            this.tag_input = Y.one('#tag-input');
            this.ok_button = Y.one('#edit-tags-ok');
            this.cancel_button = Y.one('#edit-tags-cancel');
            this.tags_edit_spinner = Y.one('#tags-edit-spinner');
        },

        test_setup_tag_entry: function() {
            module.setup_tag_entry(['project-tag']);
            // The form is created.
            var form_node = this.bug_tags_div.one('#tags-form');
            Y.Assert.isInstanceOf(Y.Node, form_node);
            Y.Assert.isInstanceOf(Y.Node, form_node.one('#tag-input'));
            Y.Assert.isInstanceOf(Y.Node, form_node.one('#tags-edit-spinner'));
            Y.Assert.isInstanceOf(Y.Node, form_node.one('#edit-tags-cancel'));
            Y.Assert.isInstanceOf(Y.Node, Y.one('.bug-tag-complete'));
        },

        test_show_activity: function() {
            // The add tags presentation is shown when the tags are removed.
            module.setup_tag_entry(['project-tag']);
            this._set_common_elements();
            module.show_activity(true);
            Y.Assert.isFalse(this.tags_edit_spinner.hasClass('hidden'));
            Y.Assert.isTrue(this.ok_button.hasClass('hidden'));
            Y.Assert.isTrue(this.cancel_button.hasClass('hidden'));
            module.show_activity(false);
            Y.Assert.isTrue(this.tags_edit_spinner.hasClass('hidden'));
            Y.Assert.isFalse(this.ok_button.hasClass('hidden'));
            Y.Assert.isFalse(this.cancel_button.hasClass('hidden'));
        },


        test_update_ui_remove_all_tags: function() {
            // The add tags presentation is shown when the tags are removed.
            module.setup_tag_entry(['project-tag']);
            this._set_common_elements();
            this.tag_list_span.set('text', '');
            module.update_ui();
            Y.Assert.areEqual('', this.tags_heading.get('text'));
            Y.Assert.areEqual('Add tags', this.tags_trigger.get('text'));
            Y.Assert.areEqual('Add tags', this.tags_trigger.get('title'));
            Y.Assert.isTrue(this.tags_trigger.hasClass('add'));
            Y.Assert.isFalse(this.tags_trigger.hasClass('action-icon'));
            Y.Assert.isFalse(this.tags_trigger.hasClass('edit'));
        },

        test_update_ui_add_tags: function() {
            // The edit tags presentation is shown when tags are added.
            module.setup_tag_entry(['project-tag']);
            var template = Y.one('#add-bug-tag-form').getContent();
            this.fixture.append(template);
            this._set_common_elements();
            this.tag_list_span.set(
                'innerHtml', '<a href="#">project-tag</a>');
            module.update_ui();
            Y.Assert.areEqual('Tags:', this.tags_heading.get('text'));
            Y.Assert.areEqual('Edit', this.tags_trigger.get('text'));
            Y.Assert.areEqual('Edit tags', this.tags_trigger.get('title'));
            Y.Assert.isTrue(this.tags_trigger.hasClass('edit'));
            Y.Assert.isTrue(this.tags_trigger.hasClass('action-icon'));
            Y.Assert.isFalse(this.tags_trigger.hasClass('add'));
        },

        test_edit: function() {
            module.setup_tag_entry(['project-tag']);
            this._set_common_elements();
            this.tags_trigger.simulate('click');
            Y.Assert.isTrue(this.tag_list_span.hasClass('hidden'));
            Y.Assert.isTrue(this.tags_trigger.hasClass('hidden'));
            Y.Assert.isFalse(this.tags_form.hasClass('hidden'));
            Y.Assert.isFalse(this.ok_button.hasClass('hidden'));
            Y.Assert.isFalse(this.cancel_button.hasClass('hidden'));
            // Check the tag-input has focus.
            var focused_element = Y.one(document.activeElement);
            Y.Assert.areEqual(focused_element, Y.one('#tag-input'));
        },

        test_cancel: function() {
            module.setup_tag_entry(['project-tag']);
            this._set_common_elements();
            this.tags_trigger.simulate('click');
            this.cancel_button.simulate('click');
            Y.Assert.isFalse(this.tag_list_span.hasClass('hidden'));
            Y.Assert.isFalse(this.tags_trigger.hasClass('hidden'));
            Y.Assert.isTrue(this.tags_form.hasClass('hidden'));
            Y.Assert.isTrue(this.tags_edit_spinner.hasClass('hidden'));
        },

        test_save_tags_success: function() {
            module.setup_tag_entry(['project-tag']);
            this._set_common_elements();
            this.tags_trigger.simulate('click');
            var mockio = new Y.lp.testing.mockio.MockIo();
            module.lp_config = {io_provider: mockio};
            this.ok_button.simulate('click');
            Y.Assert.isFalse(this.tags_edit_spinner.hasClass('hidden'));
            Y.Assert.areEqual(
                '/api/devel/bug/1', mockio.last_request.url);
            mockio.success({
                responseText: Y.JSON.stringify({
                    resource_type_link: 'Bug',
                    self_link: '/bug/1',
                    tags: ['project-tag']}),
                responseHeaders: {'Content-Type': 'application/json'}});
            Y.Assert.isFalse(this.tag_list_span.hasClass('hidden'));
            Y.Assert.isFalse(this.tags_trigger.hasClass('hidden'));
            Y.Assert.isTrue(this.tags_form.hasClass('hidden'));
            Y.Assert.isTrue(this.tags_edit_spinner.hasClass('hidden'));
            Y.Assert.isFalse(this.ok_button.hasClass('hidden'));
            Y.Assert.isFalse(this.cancel_button.hasClass('hidden'));
        },

        test_save_tags_failure: function() {
            module.setup_tag_entry(['project-tag']);
            this._set_common_elements();
            this.tags_trigger.simulate('click');
            var mockio = new Y.lp.testing.mockio.MockIo();
            module.lp_config = {io_provider: mockio};
            this.ok_button.simulate('click');
            mockio.failure({
                responseText: Y.JSON.stringify({
                    resource_type_link: 'Bug',
                    self_link: '/bug/1',
                    tags: ['project-tag']}),
                responseHeaders: {'Content-Type': 'application/json'}});
            Y.Assert.isFalse(this.ok_button.hasClass('hidden'));
            Y.Assert.isFalse(this.cancel_button.hasClass('hidden'));
            Y.Assert.isTrue(this.tags_edit_spinner.hasClass('hidden'));
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'Completer',

        setUp: function() {
            this.fixture = Y.one("#fixture");
            var template = Y.one('#form-with-bug-tags').getContent();
            this.fixture.append(template);
        },

        tearDown: function() {
            if (this.fixture !== null) {
                this.fixture.empty();
            }
            delete this.fixture;
        },

        test_setup_tag_complete: function() {
            // The Autocompleter nodes are provided.
            module.setup_tag_complete(
                'input[id="field.tag"]',['project-tag']);
            var completer_node = Y.one('.yui3-autocomplete');
            Y.Assert.isInstanceOf(Y.Node, completer_node);
            Y.Assert.isTrue(completer_node.hasClass('bug-tag-complete'));
            var completer_content = completer_node.one(
                '.yui3-autocomplete-content');
            Y.Assert.isInstanceOf(Y.Node, completer_content);
            var input = Y.one('input[id="field.tag"]');
        },

        test_render_on_focus: function() {
            // The Autocompleter nodes are provided.
            var completer = module.setup_tag_complete(
                'input[id="field.tag"]',['project-tag']);
            var input = Y.one('input[id="field.tag"]');
            var called = false;
            completer.render = function() {
                called = true;
            };
            input.simulate('focus');
            Y.Assert.isTrue(called);
        }
    }));

}, '0.1', {
    requires: ['lp.testing.runner', 'lp.testing.mockio', 'test', 'test-console',
               'lp.client', 'node-event-simulate', 'lp.bugs.tags_entry']
});
