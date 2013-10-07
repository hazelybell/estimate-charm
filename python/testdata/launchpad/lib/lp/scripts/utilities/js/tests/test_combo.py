# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import os
import shutil
import tempfile

from paste.fixture import TestApp

from lp.scripts.utilities.js.combo import (
    combine_files,
    combo_app,
    parse_url,
    )
from lp.testing import TestCase


class ComboTestBase(TestCase):

    def setUp(self):
        self.__cleanup_paths = []
        self.addCleanup(self.__cleanup)
        super(ComboTestBase, self).setUp()

    def __cleanup(self):
        for path in self.__cleanup_paths:
            if os.path.isfile(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)

    def makeFile(self, content=None, suffix="", prefix="tmp", basename=None,
                 dirname=None, path=None):
        """Create a temporary file and return the path to it.

        @param content: Initial content for the file.
        @param suffix: Suffix to be given to the file's basename.
        @param prefix: Prefix to be given to the file's basename.
        @param basename: Full basename for the file.
        @param dirname: Put file inside this directory.

        The file is removed after the test runs.
        """
        if path is not None:
            self.__cleanup_paths.append(path)
        elif basename is not None:
            if dirname is None:
                dirname = tempfile.mkdtemp()
                self.__cleanup_paths.append(dirname)
            path = os.path.join(dirname, basename)
        else:
            fd, path = tempfile.mkstemp(suffix, prefix, dirname)
            self.__cleanup_paths.append(path)
            os.close(fd)
            if content is None:
                os.unlink(path)
        if content is not None:
            file = open(path, "w")
            file.write(content)
            file.close()
        return path

    def makeDir(self, suffix="", prefix="tmp", dirname=None, path=None):
        """Create a temporary directory and return the path to it.

        @param suffix: Suffix to be given to the file's basename.
        @param prefix: Prefix to be given to the file's basename.
        @param dirname: Put directory inside this parent directory.

        The directory is removed after the test runs.
        """
        if path is not None:
            os.makedirs(path)
        else:
            path = tempfile.mkdtemp(suffix, prefix, dirname)
        self.__cleanup_paths.append(path)
        return path

    def makeSampleFile(self, root, fname, content):
        full = os.path.join(root, fname)
        parent = os.path.dirname(full)
        if not os.path.exists(parent):
            os.makedirs(parent)
        return self.makeFile(content=content, path=full)


class TestCombo(ComboTestBase):

    def test_parse_url_keeps_order(self):
        """Parsing a combo loader URL returns an ordered list of filenames."""
        self.assertEquals(
            parse_url(("http://yui.yahooapis.com/combo?"
                       "3.0.0/build/yui/yui-min.js&"
                       "3.0.0/build/oop/oop-min.js&"
                       "3.0.0/build/event-custom/event-custom-min.js&")),
            ("3.0.0/build/yui/yui-min.js",
             "3.0.0/build/oop/oop-min.js",
             "3.0.0/build/event-custom/event-custom-min.js"))

    def test_combine_files_includes_filename(self):
        """Combining files should include their relative filename at the top."""
        test_dir = self.makeDir()

        files = [
            self.makeSampleFile(
                test_dir,
                os.path.join("yui", "yui-min.js"),
                "** yui-min **"),
            self.makeSampleFile(
                test_dir,
                os.path.join("oop", "oop-min.js"),
                "** oop-min **"),
            self.makeSampleFile(
                test_dir,
                os.path.join("event-custom", "event-custom-min.js"),
                "** event-custom-min **"),
            ]

        expected = "\n".join(("// yui/yui-min.js",
                              "** yui-min **",
                              "// oop/oop-min.js",
                              "** oop-min **",
                              "// event-custom/event-custom-min.js",
                              "** event-custom-min **"))
        self.assertEquals(
            "".join(combine_files(["yui/yui-min.js",
                                   "oop/oop-min.js",
                                   "event-custom/event-custom-min.js"],
                                  root=test_dir)).strip(),
            expected)

    def test_combine_css_minifies_and_makes_relative(self):
        """
        Combining CSS files minifies and makes URLs in CSS
        declarations relative to the target path.
        """
        test_dir = self.makeDir()

        files = [
            self.makeSampleFile(
                test_dir,
                os.path.join("widget", "assets", "skins", "sam", "widget.css"),
                """\
                /* widget skin */
                .yui-widget {
                   background: url("img/bg.png");
                }
                """),
            self.makeSampleFile(
                test_dir,
                os.path.join("editor", "assets", "skins", "sam", "editor.css"),
                """\
                /* editor skin */
                .yui-editor {
                   background: url("img/bg.png");
                }
                """),
            ]

        expected = "\n".join(
            ("/* widget/assets/skins/sam/widget.css */",
             ".yui-widget{background:url(widget/assets/skins/sam/img/bg.png)}",
             "/* editor/assets/skins/sam/editor.css */",
             ".yui-editor{background:url(editor/assets/skins/sam/img/bg.png)}",
             ))
        self.assertEquals(
            "".join(combine_files(["widget/assets/skins/sam/widget.css",
                                   "editor/assets/skins/sam/editor.css"],
                                  root=test_dir)).strip(),
            expected)

    def test_combine_css_leaves_absolute_urls_untouched(self):
        """
        Combining CSS files does not touch absolute URLs in
        declarations.
        """
        test_dir = self.makeDir()

        files = [
            self.makeSampleFile(
                test_dir,
                os.path.join("widget", "assets", "skins", "sam", "widget.css"),
                """\
                /* widget skin */
                .yui-widget {
                   background: url("/static/img/bg.png");
                }
                """),
            self.makeSampleFile(
                test_dir,
                os.path.join("editor", "assets", "skins", "sam", "editor.css"),
                """\
                /* editor skin */
                .yui-editor {
                   background: url("http://foo/static/img/bg.png");
                }
                """),
            ]

        expected = "\n".join(
            ("/* widget/assets/skins/sam/widget.css */",
             ".yui-widget{background:url(/static/img/bg.png)}",
             "/* editor/assets/skins/sam/editor.css */",
             ".yui-editor{background:url(http://foo/static/img/bg.png)}",
             ))
        self.assertEquals(
            "".join(combine_files(["widget/assets/skins/sam/widget.css",
                                   "editor/assets/skins/sam/editor.css"],
                                  root=test_dir)).strip(),
            expected)

    def test_combine_css_leaves_data_uris_untouched(self):
        """
        Combining CSS files does not touch data uris in
        declarations.
        """
        test_dir = self.makeDir()

        files = [
            self.makeSampleFile(
                test_dir,
                os.path.join("widget", "assets", "skins", "sam", "widget.css"),
                """\
                /* widget skin */
                .yui-widget {
                background: url("data:image/gif;base64,base64-data");
                }
                """),
            self.makeSampleFile(
                test_dir,
                os.path.join("editor", "assets", "skins", "sam", "editor.css"),
                """\
                /* editor skin */
                .yui-editor {
                   background: url(data:image/gif;base64,base64-data);
                }
                """),
            ]

        expected = "\n".join(
            ('/* widget/assets/skins/sam/widget.css */',
             '.yui-widget{background:url("data:image/gif;base64,base64-data")}',
             '/* editor/assets/skins/sam/editor.css */',
             '.yui-editor{background:url("data:image/gif;base64,base64-data")}',
             ))
        self.assertEquals(
            "".join(combine_files(["widget/assets/skins/sam/widget.css",
                                   "editor/assets/skins/sam/editor.css"],
                                  root=test_dir)).strip(),
            expected)

    def test_combine_css_disable_minify(self):
        """
        It is possible to disable CSS minification altogether, while
        keeping the URL rewriting behavior.
        """
        test_dir = self.makeDir()

        files = [
            self.makeSampleFile(
                test_dir,
                os.path.join("widget", "assets", "skins", "sam", "widget.css"),
                "\n".join(
                    ('/* widget skin */',
                     '.yui-widget {',
                     '   background: url("img/bg.png");',
                     '}'))
                ),
            self.makeSampleFile(
                test_dir,
                os.path.join("editor", "assets", "skins", "sam", "editor.css"),
                "\n".join(('/* editor skin */',
                           '.yui-editor {',
                           '   background: url("img/bg.png");',
                           '}'))
                ),
            ]

        expected = "\n".join(
            ("/* widget/assets/skins/sam/widget.css */",
             "/* widget skin */",
             ".yui-widget {",
             "   background: url(widget/assets/skins/sam/img/bg.png);",
             "}",
             "/* editor/assets/skins/sam/editor.css */",
             "/* editor skin */",
             ".yui-editor {",
             "   background: url(editor/assets/skins/sam/img/bg.png);",
             "}",
             ))
        self.assertEquals(
            "".join(combine_files(["widget/assets/skins/sam/widget.css",
                                   "editor/assets/skins/sam/editor.css"],
                                  root=test_dir, minify_css=False)).strip(),
            expected)

    def test_combine_css_disable_rewrite_url(self):
        """
        It is possible to disable the rewriting of urls in the CSS
        file.
        """
        test_dir = self.makeDir()

        files = [
            self.makeSampleFile(
                test_dir,
                os.path.join("widget", "assets", "skins", "sam", "widget.css"),
                """\
                /* widget skin */
                .yui-widget {
                   background: url("img/bg.png");
                }
                """),
            self.makeSampleFile(
                test_dir,
                os.path.join("editor", "assets", "skins", "sam", "editor.css"),
                """\
                /* editor skin */
                .yui-editor {
                   background: url("img/bg.png");
                }
                """),
            ]

        expected = "\n".join(
            ("/* widget/assets/skins/sam/widget.css */",
             ".yui-widget{background:url(img/bg.png)}",
             "/* editor/assets/skins/sam/editor.css */",
             ".yui-editor{background:url(img/bg.png)}",
             ))
        self.assertEquals(
            "".join(combine_files(["widget/assets/skins/sam/widget.css",
                                   "editor/assets/skins/sam/editor.css"],
                                  root=test_dir, rewrite_urls=False)).strip(),
            expected)

    def test_combine_css_disable_rewrite_url_and_minify(self):
        """
        It is possible to disable both the rewriting of urls in the
        CSS file and minification, in which case the files are
        returned unchanged.
        """
        test_dir = self.makeDir()

        files = [
            self.makeSampleFile(
                test_dir,
                os.path.join("widget", "assets", "skins", "sam", "widget.css"),
                "\n".join(
                    ('/* widget skin */',
                     '.yui-widget {',
                     '   background: url("img/bg.png");',
                     '}'))
                ),
            self.makeSampleFile(
                test_dir,
                os.path.join("editor", "assets", "skins", "sam", "editor.css"),
                "\n".join(('/* editor skin */',
                           '.yui-editor {',
                           '   background: url("img/bg.png");',
                           '}'))
                ),
            ]

        expected = "\n".join(
            ('/* widget/assets/skins/sam/widget.css */',
             '/* widget skin */',
             '.yui-widget {',
             '   background: url("img/bg.png");',
             '}',
             '/* editor/assets/skins/sam/editor.css */',
             '/* editor skin */',
             '.yui-editor {',
             '   background: url("img/bg.png");',
             '}',
             ))
        self.assertEquals(
            "".join(combine_files(["widget/assets/skins/sam/widget.css",
                                   "editor/assets/skins/sam/editor.css"],
                                  root=test_dir,
                                  minify_css=False,
                                  rewrite_urls=False)).strip(),
            expected)

    def test_combine_css_adds_custom_prefix(self):
        """
        Combining CSS files minifies and makes URLs in CSS
        declarations relative to the target path. It's also possible
        to specify an additional prefix for the rewritten URLs.
        """
        test_dir = self.makeDir()

        files = [
            self.makeSampleFile(
                test_dir,
                os.path.join("widget", "assets", "skins", "sam", "widget.css"),
                """\
                /* widget skin */
                .yui-widget {
                   background: url("img/bg.png");
                }
                """),
            self.makeSampleFile(
                test_dir,
                os.path.join("editor", "assets", "skins", "sam", "editor.css"),
                """\
                /* editor skin */
                .yui-editor {
                   background: url("img/bg.png");
                }
                """),
            ]

        expected = "\n".join(
            ("/* widget/assets/skins/sam/widget.css */",
             ".yui-widget{background:url(" +
             "/static/widget/assets/skins/sam/img/bg.png)}",
             "/* editor/assets/skins/sam/editor.css */",
             ".yui-editor{background:url(" +
             "/static/editor/assets/skins/sam/img/bg.png)}",
             ))
        self.assertEquals(
            "".join(combine_files(["widget/assets/skins/sam/widget.css",
                                   "editor/assets/skins/sam/editor.css"],
                                  root=test_dir,
                                  resource_prefix="/static/")).strip(),
            expected)

    def test_missing_file_is_ignored(self):
        """If a missing file is requested we should still combine the others."""
        test_dir = self.makeDir()

        files = [
            self.makeSampleFile(
                test_dir,
                os.path.join("yui", "yui-min.js"),
                "** yui-min **"),
            self.makeSampleFile(
                test_dir,
                os.path.join("event-custom", "event-custom-min.js"),
                "** event-custom-min **"),
            ]

        expected = "\n".join(("// yui/yui-min.js",
                              "** yui-min **",
                              "// oop/oop-min.js",
                              "// [missing]",
                              "// event-custom/event-custom-min.js",
                              "** event-custom-min **"))
        self.assertEquals(
            "".join(combine_files(["yui/yui-min.js",
                                   "oop/oop-min.js",
                                   "event-custom/event-custom-min.js"],
                                  root=test_dir)).strip(),
            expected)

    def test_no_parent_hack(self):
        """If someone tries to hack going up the root, he'll get a miss."""
        test_dir = self.makeDir()
        files = [
            self.makeSampleFile(
                test_dir,
                os.path.join("oop", "oop-min.js"),
                "** oop-min **"),
            ]

        root = os.path.join(test_dir, "root", "lazr")
        os.makedirs(root)

        hack = "../../oop/oop-min.js"
        self.assertTrue(os.path.exists(os.path.join(root, hack)))

        expected = "\n".join(("// ../../oop/oop-min.js",
                              "// [missing]"))
        self.assertEquals(
            "".join(combine_files([hack], root=root)).strip(),
            expected)

    def test_rewrite_url_normalizes_parent_references(self):
        """URL references in CSS files get normalized for parent dirs."""
        test_dir = self.makeDir()
        files = [
            self.makeSampleFile(
                test_dir,
                os.path.join("yui", "base", "base.css"),
                ".foo{background-image:url(../../img.png)}"),
            ]

        expected = "\n".join(("/* yui/base/base.css */",
                              ".foo{background-image:url(img.png)}"))
        self.assertEquals(
            "".join(combine_files(files, root=test_dir)).strip(),
            expected)


    def test_no_absolute_path_hack(self):
        """If someone tries to fetch an absolute file, he'll get nothing."""
        test_dir = self.makeDir()

        hack = "/etc/passwd"
        self.assertTrue(os.path.exists("/etc/passwd"))

        expected = ""
        self.assertEquals(
            "".join(combine_files([hack], root=test_dir)).strip(),
            expected)


class TestWSGICombo(ComboTestBase):

    def setUp(self):
        super(TestWSGICombo, self).setUp()
        self.root = self.makeDir()
        self.app = TestApp(combo_app(self.root))

    def test_combo_app_sets_content_type_for_js(self):
        """The WSGI App should set a proper Content-Type for Javascript."""
        files = [
            self.makeSampleFile(
                self.root,
                os.path.join("yui", "yui-min.js"),
                "** yui-min **"),
            self.makeSampleFile(
                self.root,
                os.path.join("oop", "oop-min.js"),
                "** oop-min **"),
            self.makeSampleFile(
                self.root,
                os.path.join("event-custom", "event-custom-min.js"),
                "** event-custom-min **"),
            ]

        expected = "\n".join(("// yui/yui-min.js",
                              "** yui-min **",
                              "// oop/oop-min.js",
                              "** oop-min **",
                              "// event-custom/event-custom-min.js",
                              "** event-custom-min **"))

        res = self.app.get("/?" + "&".join(
            ["yui/yui-min.js",
             "oop/oop-min.js",
             "event-custom/event-custom-min.js"]), status=200)
        self.assertEquals(res.headers, [("Content-Type", "text/javascript")])
        self.assertEquals(res.body.strip(), expected)

    def test_combo_app_sets_content_type_for_css(self):
        """The WSGI App should set a proper Content-Type for CSS."""
        files = [
            self.makeSampleFile(
                self.root,
                os.path.join("widget", "skin", "sam", "widget.css"),
                "/* widget-skin-sam */"),
            ]

        expected = "/* widget/skin/sam/widget.css */"

        res = self.app.get("/?" + "&".join(
            ["widget/skin/sam/widget.css"]), status=200)
        self.assertEquals(res.headers, [("Content-Type", "text/css")])
        self.assertEquals(res.body.strip(), expected)

    def test_no_filename_gives_404(self):
        """If no filename is included, a 404 should be returned."""
        res = self.app.get("/", status=404)
        self.assertEquals(res.headers, [("Content-Type", "text/plain")])
        self.assertEquals(res.body, "Not Found")

