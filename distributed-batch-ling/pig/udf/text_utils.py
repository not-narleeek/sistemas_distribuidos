# -*- coding: utf-8 -*-
"""Jython UDFs for Pig token normalization."""

# Hadoop's Jython runner requires an explicit encoding declaration whenever
# non-ASCII characters (like "ñ") appear in the file. Without this header the
# traffic Pig jobs crash with `SyntaxError: Non-ASCII character ...` during
# `REGISTER` time. Declaring UTF-8 keeps the implementation portable without
# changing the existing logic.
from __future__ import annotations

import re
import unicodedata

stopwords_cache = None


def _load_stopwords(path):
    global stopwords_cache
    if stopwords_cache is not None:
        return stopwords_cache
    stopwords_cache = set()
    if path:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                token = line.strip().lower()
                if token:
                    stopwords_cache.add(token)
    return stopwords_cache


class Normalizer(object):
    """Pig Jython UDF to normalize and validate tokens."""

    def __init__(self, stopwords_path=None):
        self.stopwords_path = stopwords_path
        self._non_alpha = re.compile(r"[^a-zñ\s]")
        self._numeric = re.compile(r"^\d+$")

    def prepare(self, text):
        if text is None:
            return ""
        text = unicodedata.normalize("NFD", text)
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        text = text.lower()
        text = text.replace("\r", " ").replace("\n", " ")
        text = self._non_alpha.sub(" ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def is_stopword(self, token):
        if token is None:
            return True
        token = token.strip()
        if not token:
            return True
        stopwords = _load_stopwords(self.stopwords_path)
        return token in stopwords

    def is_valid_token(self, token):
        if token is None:
            return False
        token = token.strip()
        if len(token) < 2:
            return False
        if self._numeric.match(token):
            return False
        return not self.is_stopword(token)
