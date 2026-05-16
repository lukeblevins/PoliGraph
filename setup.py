#!/usr/bin/env python

from setuptools import setup

setup(
    name='poligrapher',
    version='0.1.0',
    author='UCI Networking Group',
    include_package_data=True,
    packages=['poligrapher', 'poligrapher.annotators', 'poligrapher.scripts'],
    install_requires=[
        "spacy",
        "anytree",
        "langdetect",
        "unidecode",
        "regex",
        "setfit",
        "transformers",
        "tldextract",
        "requests-cache",
        "requests",
        "torch",
        "networkx",
        "pyyaml",
        "playwright",
        "beautifulsoup4",
        "markdown",
        "pymupdf4llm",
    ],
)
