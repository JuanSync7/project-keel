"""
title: audit_dependencies_data — the closed vocabulary scripts/audit_dependencies.py keeps in prose after a secret word
kind: script
layer: n/a
summary: Data, not logic (CONVENTIONS §18). In the prose clause that follows a secret word in a diagnostic npm printed, scripts/audit_dependencies.py keeps a word only when it is in this vocabulary, matched without case and without the punctuation around it, and hides every other word, so a value of a shape no one named is hidden rather than shown. `LINKING_WORDS` are the function words prose puts between a secret word and its value or its cause (`the password was set to`, `token is not`). `CAUSE_WORDS` maps each word that names a cause to the message the installed npm 11 or Node.js 24 prints that holds it, quoted from npm's source or read live from Node.js. A clause ends at a sentence's end or the line's; `CLAUSE_WORDS` is how many of its words are judged one at a time, and the rest of a longer one is hidden whole. A word added here is shown wherever it follows a secret word, so a password that is one of these words is shown: add a word only from a message npm or Node.js prints. Imports nothing, reads nothing and writes nothing.
effect: read-only
"""

__all__ = ["CAUSE_WORDS", "CLAUSE_WORDS", "LINKING_WORDS"]

LINKING_WORDS = (
    "a",
    "again",
    "an",
    "and",
    "are",
    "be",
    "been",
    "by",
    "equals",
    "for",
    "from",
    "had",
    "has",
    "have",
    "in",
    "is",
    "it",
    "its",
    "likely",
    "no",
    "not",
    "now",
    "of",
    "or",
    "please",
    "probably",
    "seems",
    "set",
    "the",
    "this",
    "to",
    "try",
    "was",
    "were",
    "with",
    "you",
    "your",
)

# Each source is where the word was read, in the installed npm 11 and
# Node.js 24: _NPM_MESSAGES is npm's lib/utils/error-message.js, _NPM_FETCH
# npm-registry-fetch's lib/errors.js, and _NODE_TLS and _NODE_FS the
# `err.message` Node.js gives, read live: a TLS client on loopback against
# an expired and a self-signed certificate, and a read of an unreadable file.
_NPM_MESSAGES = "npm lib/utils/error-message.js: "
_NPM_FETCH = "npm-registry-fetch lib/errors.js: "
_NODE_TLS = "Node.js TLS err.message: "
_NODE_FS = "Node.js fs err.message: "
_HTTP = (
    "npm-registry-fetch lib/errors.js: an HTTP error reads"
    " `${res.status} ${res.statusText} - ...`, statusText "
)
# npm-registry-fetch lib/errors.js AuthError: the scheme names the registry's
# WWW-Authenticate header gives, printed after the phrase.
_NEED_AUTH = "npm-registry-fetch lib/errors.js: 'Unable to authenticate, need: ' + "
_HTTP_METHOD = (
    "npm-registry-fetch lib/errors.js: an HTTP error reads"
    " `status statusText - METHOD uri`, method "
)

CAUSE_WORDS = {
    "authentication": _NPM_FETCH + "OTP required for authentication",
    "authenticator": _NPM_MESSAGES
    + "This operation requires a one-time password from your authenticator.",
    "basic": _NEED_AUTH + "the WWW-Authenticate scheme Basic",
    "bearer": _NEED_AUTH + "the WWW-Authenticate scheme Bearer",
    "date": _NPM_MESSAGES + "your saved credentials are probably out of date.",
    "delete": _HTTP_METHOD + "DELETE",
    "denied": _NODE_FS + "EACCES: permission denied, open '<path>'",
    "expired": _NODE_TLS + "certificate has expired",
    "forbidden": _HTTP + "Forbidden (403)",
    "get": _HTTP_METHOD + "GET",
    "head": _HTTP_METHOD + "HEAD",
    "incorrect": _NPM_MESSAGES + "Incorrect or missing password.",
    "invalid": _NPM_MESSAGES + "your authentication token seems to be invalid.",
    "logging": _NPM_MESSAGES + "please try logging in again with:",
    "login": _NPM_MESSAGES
    + "'To correct this please try logging in again with:', '  npm login'",
    "missing": _NPM_MESSAGES + "Incorrect or missing password.",
    "need": _NEED_AUTH + "res.headers.get('www-authenticate')",
    "one-time": _NPM_MESSAGES + "This operation requires a one-time password.",
    "otp": _NPM_FETCH + "OTP required for authentication",
    "out": _NPM_MESSAGES + "your saved credentials are probably out of date.",
    "patch": _HTTP_METHOD + "PATCH",
    "post": _HTTP_METHOD + "POST",
    "provided": _NPM_MESSAGES + "If you already provided a one-time password",
    "put": _HTTP_METHOD + "PUT",
    "realm": _NEED_AUTH + "the auth-param of a WWW-Authenticate challenge, realm=",
    "rejected": _NPM_MESSAGES + "The operation was rejected by your operating system.",
    "required": _NPM_FETCH + "OTP required for authentication",
    "requires": _NPM_MESSAGES + "This operation requires a one-time password.",
    "self-signed": _NODE_TLS
    + "self-signed certificate; if the root CA is installed locally, ...",
    "timed": _NPM_MESSAGES + "or it timed out. Please try again.",
    "unauthorized": _HTTP + "Unauthorized (401)",
}

# How many words a clause judges one at a time. A clause that reaches it
# before its sentence ends has the rest of that sentence hidden whole, so
# the bound can cost shown words and can show none. npm's longest clause
# after a secret word is 13 words ("password then it is likely that you
# either typoed it, or it timed out.").
CLAUSE_WORDS = 16
