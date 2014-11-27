# HTTP API for [UnnaturalCode][]

# Run

    python -m unnaturalcode.http

# Test

With [nose2][]

      nose2 unnaturalcode.http.test_server

[nose2]: https://github.com/nose-devs/nose2

# All rooted on resource `/{corpus}`

 * Currently, only the `py` corpus is supported. Obviously, `py` is the
   occam-π corpus.


# Corpus info—`GET /{corpus}/`

Returns metadata for the given corpus. Metadata includes:

 * `name`
 * `description`
 * `language`—programming or otherwise
 * `order`— order of the *n*-gram
 * `smoothing`—Probably always `ModKN` ([Modified Kneser-Ney][ModKN])

[ModKN]: http://en.wikipedia.org/wiki/N-gram#Smoothing_techniques


# Predict—`GET /{corpus}/predict/{prefix*}`

     GET /py/predict/<unk>/for/i/in HTTP/1.1

     {"suggestions": [3.45, ["range", "(", "5", ")", ":"]]}

## Mandatory arguments

The prefix must be given in the path.

### `{context*}`

Preceding token context. The more tokens provided, the better, but
you'll probably want to have at least three in most cases.



# Predict—`POST /{corpus}/predict/`

     POST /py/predict/ HTTP/1.1
     Content-Type: multipart/form-data; ...

     [...file upload...]

     {"suggestions": [3.45, ["range", "(", "5", ")", ":"]]}

## Mandatory arguments

Use one of `?f` or `?s`:

### `?f`

Upload a file in a multipart message as `?f`. The file will
automatically be tokenized.

### `?s`

Post a string excerpt `?s`. The file will automatically be tokenized.



# Cross Entropy—`POST /{corpus}/xentropy`

Compute the cross entropy of a file with respect to the corpus. Gives
a number from 0 to ∞ that indicates how surprised the language model is
by this file.

## Mandatory arguments

Use one of `?f` or `?s`:

### `?f`

Upload a file in a multipart message as `?f`. The file will
automatically be tokenized.

### `?s`

Post a string excerpt `?s`. The file will automatically be tokenized.



# Train—`POST /{corpus}/`

Trains the corpus with a file. 

## Mandatory arguments

Use one of `?f` or `?s`:

### `?f`

Upload a file in a multipart message as `?f`. The file will
automatically be tokenized.

### `?s`

Post a string excerpt `?s`. The file will automatically be tokenized.



# Licensing

Like [UnnaturalCode][], UnnaturalCode-HTTP is licensed under the AGPL3+.

© 2014 Eddie Antonio Santos

UnnaturalCode-HTTP is free software: you can redistribute it and/or
modify it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

UnnaturalCode-HTTP is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero
General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with UnnaturalCode-HTTP. If not, see http://www.gnu.org/licenses/.

[UnnaturalCode]: https://github.com/orezpraw/unnaturalcode
