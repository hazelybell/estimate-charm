/* Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.anim.test', function(Y) {
    var Assert = Y.Assert,  // For easy access to isTrue(), etc.
        ArrayAssert = Y.ArrayAssert;
    var tests = Y.namespace('lp.anim.test');

    tests.suite = new Y.Test.Suite('Anim Tets');
    tests.suite.add(new Y.Test.Case({
        name: 'TestAnim',

        setUp: function() {
            this.workspace = Y.Node.create(
                '<div id="workspace">'
                + '<table id="anim-table">'
                + '<tr id="anim-table-tr">'
                + '<td id="anim-table-td1" style="background: #eeeeee">foo</td>'
                + '<td id="anim-table-td2" style="background: #eeeeee">bar</td>'
                + '</tr></table></div>'
            );
            Y.one(document.body).append(this.workspace);
        },

        tearDown: function() {
            this.workspace.remove(true);
        },

        test_resolveNodeListFrom_selector: function() {
            var selector = '#anim-table-td1';
            var nodelist = tests.resolveNodeListFrom(selector);
            Assert.isInstanceOf(Y.NodeList, nodelist);
            ArrayAssert.itemsAreSame(
                [Y.one(selector)], nodelist._nodes.map(Y.one));
        },

        test_resolveNodeListFrom_node: function() {
            var node = Y.one('#anim-table-td1');
            var nodelist = tests.resolveNodeListFrom(node);
            Assert.isInstanceOf(Y.NodeList, nodelist);
            ArrayAssert.itemsAreSame(
                [node], nodelist._nodes.map(Y.one));
        },

        test_resolveNodeListFrom_node_list: function() {
            var nodelist_orig = Y.all('#anim-table td');
            var nodelist = tests.resolveNodeListFrom(nodelist_orig);
            Assert.isInstanceOf(Y.NodeList, nodelist);
            Assert.areSame(nodelist, nodelist_orig);
        },

        test_resolveNodeListFrom_anythine_else: function() {
            var succeed = true;
            try {
                var nodelist = tests.resolveNodeListFrom(
                    {crazy: true, broken: 'definitely'});
            } catch(e) {
                succeed = false;
            }
            Assert.isFalse(succeed, "Somehow, we're cleverer than we thought.");
        },

        test_green_flash_td1: function() {
            // works as expected on a single node,
            // without coercion into a NodeList here
            var node = Y.one('#anim-table-td1');
            var bgcolor = node.getStyle('backgroundColor');
            var anim = Y.lp.anim.green_flash(
                {node: node,
                 to: {backgroundColor: bgcolor},
                 duration: 0.2}
            );
            anim.run();
            this.wait(function() {
                Assert.areEqual(
                    bgcolor,
                    node.getStyle('backgroundColor'),
                    'background colors do not match'
                    );
                }, 500
            );
        },

        test_green_flash_td1_by_selector: function() {
            // works as expected on a single node selector,
            // without coercion into a NodeList here
            var node = Y.one('#anim-table-td1');
            var bgcolor = node.getStyle('backgroundColor');
            var anim = Y.lp.anim.green_flash(
                {node: '#anim-table-td1',
                 to: {backgroundColor: bgcolor},
                 duration: 0.2}
            );
            anim.run();
            this.wait(function() {
                Assert.areEqual(
                    bgcolor,
                    node.getStyle('backgroundColor'),
                    'background colors do not match'
                    );
                }, 500
            );
        },

        test_green_flash_multi: function() {
            // works with a native NodeList as well
            var nodelist = Y.all('#anim-table td');
            var red = '#ff0000';
            var backgrounds = [];
            Y.each(nodelist, function(n) {
                backgrounds.push({bg: n.getStyle('backgroundColor'), node: n});
            });
            var anim = Y.lp.anim.green_flash(
                {node: nodelist,
                 to: {backgroundColor: red},
                 duration: 5}
            );
            anim.run();
            this.wait(function() {
                Assert.areNotEqual(
                    backgrounds[0].node.getStyle('backgroundColor'),
                    red,
                    'background of 0 has mysteriously jumped to the end color.'
                );
                Assert.areNotEqual(
                    backgrounds[1].node.getStyle('backgroundColor'),
                    red,
                    'background of 1 has mysteriously jumped to the end color.'
                );
                Assert.areNotEqual(
                    backgrounds[0].node.getStyle('backgroundColor'),
                    backgrounds[0].bg,
                    'background of 0 has not changed at all.'
                );
                Assert.areNotEqual(
                    backgrounds[1].node.getStyle('backgroundColor'),
                    backgrounds[1].bg,
                    'background of 1 has not changed at all.'
                );
            }, 1500);
        },

        test_green_flash_multi_by_selector: function() {
            // works with a native NodeList as well
            var nodelist = Y.all('#anim-table td');
            var red = '#ff0000';
            var backgrounds = [];
            Y.each(nodelist, function(n) {
                backgrounds.push({bg: n.getStyle('backgroundColor'), node: n});
            });
            var anim = Y.lp.anim.green_flash(
                {node: '#anim-table td',
                 to: {backgroundColor: red},
                 duration: 2}
            );
            anim.run();
            this.wait(function() {
                Assert.areNotEqual(
                    backgrounds[0].node.getStyle('backgroundColor'),
                    red,
                    'background of 0 has mysteriously jumped to the end color.'
                );
                Assert.areNotEqual(
                    backgrounds[1].node.getStyle('backgroundColor'),
                    red,
                    'background of 1 has mysteriously jumped to the end color.'
                );
                Assert.areNotEqual(
                    backgrounds[0].node.getStyle('backgroundColor'),
                    backgrounds[0].bg,
                    'background of 0 has not changed at all.'
                );
                Assert.areNotEqual(
                    backgrounds[1].node.getStyle('backgroundColor'),
                    backgrounds[1].bg,
                    'background of 1 has not changed at all.'
                );
            }, 500);
        },

        test_on: function() {
            // Anim.on delegates to its component animations.
            var targets = [];
            var anim = new Y.lp.anim.Anim({node: "#anim-table td"});
            Assert.areSame(2, anim._anims.length);
            anim.on("start", function(event) { targets.push(event.target); });
            anim.run();
            Assert.areSame(2, targets.length);
            ArrayAssert.containsItems(anim._anims, targets);
        }

    }));

}, "0.1", {"requires": [
               'test', 'node', 'lp.anim', 'event',
               'event-simulate']});
