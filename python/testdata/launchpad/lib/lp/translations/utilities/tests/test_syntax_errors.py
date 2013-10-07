# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from unittest import (
    TestCase,
    TestLoader,
    TestSuite,
    TextTestRunner,
    )

from lp.translations.interfaces.translationimporter import (
    TranslationFormatInvalidInputError,
    TranslationFormatSyntaxError,
    )


class TranslationFormatInvalidInputErrorTest(TestCase):
    """Test `TranslationFormatInvalidInputError`."""

    def testRepresentInvalidInputError(self):
        # Test basic string conversion.
        exception = TranslationFormatInvalidInputError()
        self.assertEqual(str(exception), "Invalid input")

        exception = TranslationFormatInvalidInputError(filename="foo")
        self.assertEqual(str(exception), "foo: Invalid input")

        exception = TranslationFormatInvalidInputError(line_number=9)
        self.assertEqual(str(exception), "Line 9: Invalid input")

        exception = TranslationFormatInvalidInputError(
            filename="foo", line_number=9)
        self.assertEqual(str(exception), "foo, line 9: Invalid input")

        exception = TranslationFormatInvalidInputError(message="message")
        self.assertEqual(str(exception), "message")

        exception = TranslationFormatInvalidInputError(
            filename="foo", message="message")
        self.assertEqual(str(exception), "foo: message")

        exception = TranslationFormatInvalidInputError(
            line_number=9, message="message")
        self.assertEqual(str(exception), "Line 9: message")

        exception = TranslationFormatInvalidInputError(
            filename="foo", line_number=9, message="message")
        self.assertEqual(str(exception), "foo, line 9: message")

    def testNonAsciiInvalidInputError(self):
        # Test input errors that use non-ascii characters.

        # Here's one with a Thai "r" character in its message.
        exception = TranslationFormatInvalidInputError(
            filename=u"ror-rua", line_number=2, message=u"r\u0e23")
        representation = str(exception)
        self.assertEqual(representation, "ror-rua, line 2: r\\u0e23")

        # And here's one with the Khmer equivalent in its filename.
        exception = TranslationFormatInvalidInputError(
            filename=u"ro-\u179a", message=u"hok baay heuy?")
        representation = str(exception)
        self.assertEqual(representation, "ro-\\u179a: hok baay heuy?")



class TranslationFormatSyntaxErrorTest(TestCase):
    """Test `TranslationFormatSyntaxError`."""

    def testRepresentSyntaxError(self):
        # Test string conversion.  Most code is shared with
        # TranslationFormatInvalidInputError, so no need to test quite as
        # extensively.
        exception = TranslationFormatSyntaxError()
        self.assertEqual(str(exception), "Unknown syntax error")

        exception = TranslationFormatSyntaxError(filename="foo", message="x")
        self.assertEqual(str(exception), "foo: x")

    def testNonAsciiSyntaxError(self):
        # Test against non-ascii characters.
        exception = TranslationFormatSyntaxError(filename=u"khor-khai-\u0e01",
            line_number=4, message=u"khor-khai-\u0e02")
        self.assertEqual(str(exception),
            "khor-khai-\\u0e01, line 4: khor-khai-\u0e02")


def test_suite():
    suite = TestSuite()
    loader = TestLoader()
    suite.addTest(loader.loadTestsFromTestCase(
        TranslationFormatInvalidInputErrorTest))
    suite.addTest(loader.loadTestsFromTestCase(
        TranslationFormatSyntaxErrorTest))
    return suite


if __name__ == '__main__':
    TextTestRunner().run(test_suite())

