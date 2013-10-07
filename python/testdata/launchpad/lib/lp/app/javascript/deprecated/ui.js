/* Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Deprecated javascript in Launchpad.
 *
 * @module Y.lp.deprecated-ui
 */
YUI.add('lp.deprecated.ui', function(Y) {

    var module = Y.namespace('lp.deprecated.ui');

    module.update_field = function(selector, content)
    {
      if (Y.Lang.isString(content))
        content = Y.Escape.html(content);

      var element = Y.one(selector);
      element.setContent(content);
      Y.lp.anim.green_flash({node:element}).run();
    };

  }, "0.1", {"requires": ["node", "escape", "lp.anim"]}
);
