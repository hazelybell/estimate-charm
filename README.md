# Restful Prediction Service

Resources needed:

 * `POST` train model with file
 * `GET` predict from prefix
 * `GET` tokenize string/file (Debug)
 * `POST` cross entropy for file
 * ~~`POST` Who's that corpus!~~

# All rooted on resource `/{corpus}`

### `{corpus}`

sets the language model to use. Possible values: `py`, `java`, `js`,
`rb`, etc...



# `GET /{corpus}/` -- Corpus info

Fetches metadata for the given corpus. Metadata includes:

 * `fullname`
 * `last_updated`
 * `description`
 * `language` -- programming or otherwise
 * `order`
 * `smoothing` -- Probably always `ModKN`
 * `vocabulary`
   * `size`
   * `categories` -- lists syntactic categories



# `GET /{corpus}/predict/{context*}` -- Predict

     GET /py/predict/$-:kw-for HTTP/1.1
     
     {"results":[["i", "in", "range", "(", "10", ")", ":"]]}


## Mandatory arguments

Must give context either as query `?context` or as context path.

### `{context*}`

Preceding token context. The more tokens provided, the better. See
[Context format](#context-format).

### `?context` or `?c`

Context *as a string*. The engine itself should tokenize this based on
the environment.



# `POST/GET /{corpus}/xentropy` -- calculate cross entropy

## Mandatory arguments

Either `?f` for an entire file (may be provided more than once?), or
`?c` for "context"



# `POST /{corpus}/`

Trains the corpus with some tokens from a specific source.

## Mandatory arguments

### `?file` or `?f`

A plain-text file that will be tokenized and trained upon.



# Context Format

## Formal Grammar

    token-list  = token
                / token ":" token-list

    token       = [ syncat "-" ] chars

    chars       = { ~all characters other than ":"~ }
    syncat      = [ ~all characters other than ":" and "-"~ ]

# TODO

Gotta write install and how to do VirutalEnv stuff. I'm rocking the
VirutalEnvWrapper so... it's a bit magical.

# Joshnotes

 * train some tokens.
 * n-gram query needs:
    - next token
    - find cross entropy with respect to the corpus: sliding window query
    - tokenization? Client-side or server-side? Both?
 - low priority to: guess that corpus!
 - Keep in mind local corpus.
 - ~~AI MODE!!!!!!~~

Start with UnnaturalCode! It does cross entropy and easily does
multi-corpus.

