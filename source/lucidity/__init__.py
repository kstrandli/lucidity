# :coding: utf-8
# :copyright: Copyright (c) 2013 Martin Pengelly-Phillips
# :license: See LICENSE.txt.

from ._version import __version__
from .error import (
    ParseError,
    FormatError,
    NotFound
)

from .template import (
    Template,
    Resolver,
    discover_templates,
    parse,
    format,
    get_template
)

__all__ = [
    "__version__",
    "ParseError",
    "FormatError",
    "NotFound",
    "Template",
    "Resolver",
    "discover_templates",
    "parse",
    "format",
    "get_template",
]
