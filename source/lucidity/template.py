# :coding: utf-8
# :copyright: Copyright (c) 2013 Martin Pengelly-Phillips
# :license: See LICENSE.txt.

import os
import re
import imp
import abc
import sys
import uuid
import functools
from collections import defaultdict

from . import error

# Type of a RegexObject for isinstance check.
_RegexType = type(re.compile(''))


class Template(object):
    '''A template.'''

    _STRIP_EXPRESSION_REGEX = re.compile(r'{(.+?)(:(\\}|.)+?)}')
    _PLAIN_PLACEHOLDER_REGEX = re.compile(r'{(.+?)}')
    _TEMPLATE_REFERENCE_REGEX = re.compile(r'{@(?P<reference>.+?)}')

    ANCHOR_START, ANCHOR_END, ANCHOR_BOTH = (1, 2, 3)

    RELAXED, STRICT = (1, 2)

    def __init__(self, name, pattern, anchor=ANCHOR_START,
                 default_placeholder_expression='[\w_.\-]+',
                 duplicate_placeholder_mode=RELAXED,
                 template_resolver=None):
        '''Initialise with *name* and *pattern*.

        *anchor* determines how the pattern is anchored during a parse. A
        value of :attr:`~Template.ANCHOR_START` (the default) will match the
        pattern against the start of a path. :attr:`~Template.ANCHOR_END` will
        match against the end of a path. To anchor at both the start and end
        (a full path match) use :attr:`~Template.ANCHOR_BOTH`. Finally,
        ``None`` will try to match the pattern once anywhere in the path.

        *duplicate_placeholder_mode* determines how duplicate placeholders will
        be handled during parsing. :attr:`~Template.RELAXED` mode extracts the
        last matching value without checking the other values.
        :attr:`~Template.STRICT` mode ensures that all duplicate placeholders
        extract the same value and raises :exc:`~error.ParseError` if
        they do not.

        If *template_resolver* is supplied, use it to resolve any template
        references in the *pattern* during operations. It should conform to the
        :class:`Resolver` interface. It can be changed at any time on the
        instance to affect future operations.

        '''
        super(Template, self).__init__()
        self.duplicate_placeholder_mode = duplicate_placeholder_mode
        self.template_resolver = template_resolver

        self._default_placeholder_expression = default_placeholder_expression
        self._period_code = '_LPD_'
        self._at_code = '_WXV_'
        self._name = name
        self._pattern = pattern
        self._anchor = anchor

        # Check that supplied pattern is valid and able to be compiled.
        self._construct_regular_expression(self.pattern)

    def __repr__(self):
        '''Return unambiguous representation of template.'''
        return '{0}(name={1!r}, pattern={2!r})'.format(
            self.__class__.__name__, self.name, self.pattern
        )

    @property
    def name(self):
        '''Return name of template.'''
        return self._name

    @property
    def pattern(self):
        '''Return template pattern.'''
        return self._pattern

    def expanded_pattern(self):
        '''Return pattern with all referenced templates expanded recursively.

        Raise :exc:`error.ResolveError` if pattern contains a
        reference that cannot be resolved by currently set template_resolver.

        '''
        return self._TEMPLATE_REFERENCE_REGEX.sub(
            self._expand_reference, self.pattern
        )

    def _expand_reference(self, match):
        '''Expand reference represented by *match*.'''
        reference = match.group('reference')

        if self.template_resolver is None:
            raise error.ResolveError(
                'Failed to resolve reference {0!r} as no template '
                'resolver set.'
                .format(reference)
            )

        template = self.template_resolver.get(reference)
        if template is None:
            raise error.ResolveError(
                'Failed to resolve reference {0!r} using template resolver.'
                .format(reference)
            )

        return template.expanded_pattern()

    def parse(self, path):
        '''Return dictionary of data extracted from *path* using this template.

        Raise :py:class:`~error.ParseError` if *path* is not
        parsable by this template.

        '''
        # Construct regular expression for expanded pattern.
        regex = self._construct_regular_expression(self.expanded_pattern())

        # Parse.
        parsed = {}

        match = regex.search(path)
        if match:
            data = {}
            for key, value in sorted(match.groupdict().items()):
                # Strip number that was added to make group name unique.
                key = key[:-3]

                # If strict mode enabled for duplicate placeholders,
                # ensure that all duplicate placeholders extract the
                # same value.
                if self.duplicate_placeholder_mode == self.STRICT:
                    if key in parsed:
                        if parsed[key] != value:
                            raise error.ParseError(
                                'Different extracted values for placeholder '
                                '{0!r} detected. Values were {1!r} and {2!r}.'
                                .format(key, parsed[key], value)
                            )
                    else:
                        parsed[key] = value

                # Expand dot notation keys into nested dictionaries.
                target = data

                parts = key.split(self._period_code)
                for part in parts[:-1]:
                    target = target.setdefault(part, {})

                target[parts[-1]] = value

            return data

        else:
            raise error.ParseError(
                'Path {0!r} did not match template pattern.'.format(path)
            )

    def format(self, data):
        '''Return a path formatted by applying *data* to this template.

        Raise :py:class:`~error.FormatError` if *data* does not
        supply enough information to fill the template fields.

        '''

        format_specification = self._construct_format_specification(
            self.expanded_pattern()
        )

        return self._PLAIN_PLACEHOLDER_REGEX.sub(
            functools.partial(self._format, data=data),
            format_specification
        )

    def _format(self, match, data):
        '''Return value from data for *match*.'''
        placeholder = match.group(1)
        parts = placeholder.split('.')

        try:
            value = data
            for part in parts:
                value = value[part]

        except (TypeError, KeyError):
            raise error.FormatError(
                'Could not format data {0!r} due to missing key {1!r}.'
                .format(data, placeholder)
            )

        else:
            return value

    def keys(self):
        '''Return unique set of placeholders in pattern.'''
        format_specification = self._construct_format_specification(
            self.expanded_pattern()
        )
        return set(self._PLAIN_PLACEHOLDER_REGEX.findall(format_specification))

    def references(self):
        '''Return unique set of referenced templates in pattern.'''
        format_specification = self._construct_format_specification(
            self.pattern
        )
        return set(self._TEMPLATE_REFERENCE_REGEX.findall(
            format_specification))

    def _construct_format_specification(self, pattern):
        '''Return format specification from *pattern*.'''
        return self._STRIP_EXPRESSION_REGEX.sub('{\g<1>}', pattern)

    def _construct_regular_expression(self, pattern):
        '''Return a regular expression to represent *pattern*.'''
        # Escape non-placeholder components.
        expression = re.sub(
            r'(?P<placeholder>{(.+?)(:(\\}|.)+?)?})|(?P<other>.+?)',
            self._escape,
            pattern
        )

        # Replace placeholders with regex pattern.
        expression = re.sub(
            r'{(?P<placeholder>.+?)(:(?P<expression>(\\}|.)+?))?}',
            functools.partial(
                self._convert, placeholder_count=defaultdict(int)
            ),
            expression
        )

        if self._anchor is not None:
            if bool(self._anchor & self.ANCHOR_START):
                expression = '^{0}'.format(expression)

            if bool(self._anchor & self.ANCHOR_END):
                expression = '{0}$'.format(expression)

        # Compile expression.
        try:
            compiled = re.compile(expression)
        except re.error as error:
            if any([
                'bad group name' in str(error),
                'bad character in group name' in str(error)
            ]):
                raise ValueError('Placeholder name contains invalid '
                                 'characters.')
            else:
                _, value, traceback = sys.exc_info()
                message = 'Invalid pattern: {0}'.format(value)
                raise ValueError(message, traceback)

        return compiled

    def _convert(self, match, placeholder_count):
        '''Return a regular expression to represent *match*.

        *placeholder_count* should be a `defaultdict(int)` that will be used to
        store counts of unique placeholder names.

        '''
        placeholder_name = match.group('placeholder')

        # Support at symbol (@) as referenced template indicator. Currently,
        # this symbol not a valid character for a group name in the standard
        # Python regex library. Rather than rewrite or monkey patch the library
        # work around the restriction with a unique identifier.
        placeholder_name = placeholder_name.replace('@', self._at_code)

        # Support period (.) as nested key indicator. Currently, a period is
        # not a valid character for a group name in the standard Python regex
        # library. Rather than rewrite or monkey patch the library work around
        # the restriction with a unique identifier.
        placeholder_name = placeholder_name.replace('.', self._period_code)

        # The re module does not support duplicate group names. To support
        # duplicate placeholder names in templates add a unique count to the
        # regular expression group name and strip it later during parse.
        placeholder_count[placeholder_name] += 1
        placeholder_name += '{0:03d}'.format(
            placeholder_count[placeholder_name]
        )

        expression = match.group('expression')
        if expression is None:
            expression = self._default_placeholder_expression

        # Un-escape potentially escaped characters in expression.
        expression = expression.replace('\{', '{').replace('\}', '}')

        return r'(?P<{0}>{1})'.format(placeholder_name, expression)

    def _escape(self, match):
        '''Escape matched 'other' group value.'''
        groups = match.groupdict()
        if groups['other'] is not None:
            return re.escape(groups['other'])

        return groups['placeholder']


class Resolver(object):
    '''Template resolver interface.'''

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def get(self, template_name, default=None):
        '''Return template that matches *template_name*.

        If no template matches then return *default*.

        '''
        return default

    @classmethod
    def __subclasshook__(cls, subclass):
        '''Return whether *subclass* fulfils this interface.'''
        if cls is Resolver:
            return callable(getattr(subclass, 'get', None))

        return NotImplemented


def discover_templates(paths=None, recursive=True):
    '''Search *paths* for mount points and load templates from them.

    *paths* should be a list of filesystem paths to search for mount points.
    If not specified will try to use value from environment variable
    :envvar:`LUCIDITY_TEMPLATE_PATH`.

    A mount point is a Python file that defines a 'register' function. The
    function should return a list of instantiated
    :py:class:`~lucidity.template.Template` objects.

    If *recursive* is True (the default) then all directories under a path
    will also be searched.

    '''
    templates = []

    if paths is None:
        paths = os.environ.get('LUCIDITY_TEMPLATE_PATH', '').split(os.pathsep)

    for path in paths:
        for base, directories, filenames in os.walk(path):
            for filename in filenames:
                _, extension = os.path.splitext(filename)
                if extension != '.py':
                    continue

                module_path = os.path.join(base, filename)
                module_name = uuid.uuid4().hex
                module = imp.load_source(module_name, module_path)
                try:
                    registered = module.register()
                except AttributeError:
                    pass
                else:
                    if registered:
                        templates.extend(registered)

            if not recursive:
                del directories[:]

    return templates


def parse(path, templates):
    '''Parse *path* against *templates*.

    *path* should be a string to parse.

    *templates* should be a list of :py:class:`~lucidity.template.Template`
    instances in the order that they should be tried.

    Return ``(data, template)`` from first successful parse.

    Raise :py:class:`~error.ParseError` if *path* is not
    parseable by any of the supplied *templates*.

    '''
    for template in templates:
        try:
            data = template.parse(path)
        except error.ParseError:
            continue
        else:
            return (data, template)

    raise error.ParseError(
        'Path {0!r} did not match any of the supplied template patterns.'
        .format(path)
    )


def format(data, templates):  # @ReservedAssignment
    '''Format *data* using *templates*.

    *data* should be a dictionary of data to format into a path.

    *templates* should be a list of :py:class:`~lucidity.template.Template`
    instances in the order that they should be tried.

    Return ``(path, template)`` from first successful format.

    Raise :py:class:`~error.FormatError` if *data* is not
    formattable by any of the supplied *templates*.


    '''
    for template in templates:
        try:
            path = template.format(data)
        except error.FormatError:
            continue
        else:
            return (path, template)

    raise error.FormatError(
        'Data {0!r} was not formattable by any of the supplied templates.'
        .format(data)
    )


def get_template(name, templates):
    '''Retrieve a template from *templates* by *name*.

    Raise :py:exc:`~error.NotFound` if no matching template with
    *name* found in *templates*.

    '''
    for template in templates:
        if template.name == name:
            return template

    raise error.NotFound(
        '{0} template not found in specified templates.'.format(name)
    )
