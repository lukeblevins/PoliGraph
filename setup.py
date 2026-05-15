#!/usr/bin/env python

from setuptools import setup

setup(
    name='poligrapher',
    author='UCI Networking Group',
    include_package_data=True,
    packages=['poligrapher', 'poligrapher.annotators', 'poligrapher.scripts'],
    install_requires=[
        "spacy>=3.0",
        "anytree>=2.8",
        "langdetect>=1.0",
        "unidecode>=1.3",
        "regex>=2023.0",
        "setfit>=1.0,<2.0",
        "transformers>=4.30,<5.0",
        "tldextract>=3.0",
        "requests-cache>=1.0",
        "requests>=2.28",
        "torch>=2.0",
        "networkx>=3.0",
        "pyyaml>=6.0",
        "playwright>=1.45",
        "beautifulsoup4>=4.12",
        "markdown>=3.4",
        "pymupdf4llm",
    ],
)
