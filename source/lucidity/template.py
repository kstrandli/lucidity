# :coding: utf-8
# :copyright: Copyright (c) 2013 Martin Pengelly-Phillips
# :license: See LICENSE.txt.

import abc
import sys
import re
import functools
from collections import defaultdict

import lucidity.error

# Type of a RegexObject for isinstance check.
_RegexType = type(re.compile(''))


class Template(object):
    '''A template.'''

    _STRIP_EXPRESSION_REGEX = re.compile(r'{(.+?)(:(\\}|.)+?)}')
    _PLAIN_PLACEHOLDER_REGEX = re.compile(r'{(.+?)}')
    _TEMPLATE_REFERENCE_REGEX = re.compile(r'{@(?P<reference>.+?)}')
    _OPTIONAL_KEY_REGEX = re.compile(r'(\[.+?\])')
    
    ANCHOR_START, ANCHOR_END, ANCHOR_BOTH = (1, 2, 3)

    RELAXED, STRICT = (1, 2)

    def __init__(self, name, pattern, anchor=ANCHOR_BOTH,
                 default_placeholder_expression='[A-Za-z0-9\-]+',
                 duplicate_placeholder_mode=STRICT,
                 template_resolver=None, key_resolver=None):
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
        extract the same value and raises :exc:`~lucidity.error.ParseError` if
        they do not.

        If *template_resolver* is supplied, use it to resolve any template
        references in the *pattern* during operations. It should conform to the
        :class:`Resolver` interface. It can be changed at any time on the
        instance to affect future operations.

        '''
        super(Template, self).__init__()
        self.duplicate_placeholder_mode = duplicate_placeholder_mode
        self.template_resolver = template_resolver
        self.key_resolver = key_resolver

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

        Raise :exc:`lucidity.error.ResolveError` if pattern contains a reference
        that cannot be resolved by currently set template_resolver.

        '''
        return self._TEMPLATE_REFERENCE_REGEX.sub(
            self._expand_reference, self.pattern
        )

    def _expand_reference(self, match):
        '''Expand reference represented by *match*.'''
        reference = match.group('reference')

        if self.template_resolver is None:
            raise lucidity.error.ResolveError(
                'Failed to resolve reference {0!r} as no template resolver set.'
                .format(reference)
            )

        template = self.template_resolver.get(reference)
        if template is None:
            raise lucidity.error.ResolveError(
                'Failed to resolve reference {0!r} using template resolver.'
                .format(reference)
            )

        return template.expanded_pattern()

    def parse(self, path):
        '''Return dictionary of data extracted from *path* using this template.

        Raise :py:class:`~lucidity.error.ParseError` if *path* is not
        parsable by this template.

        '''
        # Construct a list of regular expression for expanded pattern.
        regexes = self._construct_regular_expression(self.expanded_pattern())
        # Parse.
        parsed = {}
        for regex in regexes:
            match = regex.search(path)
            
            if match:
                data = {}
                for key, value in sorted(match.groupdict().items()):
                    # Strip number that was added to make group name unique.
                    key = key[:-3]
    
                    # If strict mode enabled for duplicate placeholders, ensure that
                    # all duplicate placeholders extract the same value.
                    if self.duplicate_placeholder_mode == self.STRICT:
                        if key in parsed:
                            if parsed[key] != value:
                                raise lucidity.error.ParseError(
                                    'Different extracted values for placeholder '
                                    '{0!r} detected. Values were {1!r} and {2!r}.'
                                    .format(key, parsed[key], value)
                                )
                        else:
                            if value:
                                parsed[key] = value
    
                    # Expand dot notation keys into nested dictionaries.
                    target = data
     
                    parts = key.split(self._period_code)
                    for part in parts[:-1]:
                        target = target.setdefault(part, {})
     
                    target[parts[-1]] = value
                
                newData=dict()
                for key,value in data.items():
                    if value != None:
                        newData[key]=value
                return newData
    
        else:
            raise lucidity.error.ParseError(
                'Path {0!r} did not match template pattern.'.format(path)
            )

    def missing(self, data, ignoreOptionals=False):
        '''Returns a set of missing keys
        optional keys are ignored/subtracted
        '''
        data_keys = set(data.keys())
        if self.key_resolver:
            new_data_keys = list()
            for key in data_keys:
                if key in self.key_resolver:
                    new_data_keys.append(self.key_resolver.get(key))
                else:
                    new_data_keys.append(key)
            data_keys = new_data_keys
        all_key = self.keys().difference(data_keys)
        if ignoreOptionals:
            return all_key
        minus_opt = all_key.difference(self.optional_keys())
        return minus_opt

    def apply_fields(self,data,abstract=False):
        '''
        here for convenience
        
        :param data: dict of fields
        :param abstract: if there are lucidity.key objects with an abstract key the formatting will use the abstract definition
        '''
        self.format(data, abstract=abstract)

    def format(self, data, abstract=False):
        '''Return a path formatted by applying *data* to this template.

        Raise :py:class:`~lucidity.error.FormatError` if *data* does not
        supply enough information to fill the template fields.

        '''

        format_specification = self._construct_format_specification(
            self.expanded_pattern()
        )
        
        #remove all missing optional keys from the format spec   
        format_specification = re.sub(
            self._OPTIONAL_KEY_REGEX,
            functools.partial(self._remove_optional_keys, data = data),
            format_specification
            )

        return self._PLAIN_PLACEHOLDER_REGEX.sub(
            functools.partial(self._format, data=data,abstract=abstract),
            format_specification
        )

    def _format(self, match, data, abstract= False):
        '''Return value from data for *match*.'''
        
        placeholder = match.group(1)
        parts = placeholder.split('.')
        try:
            value = data
            for part in parts:
                value = value[part]
                if part in self.key_resolver:
                    key = self.key_resolver.get(part)
                    key.setValue(value)
                    value = str(key)
                    if abstract and key.abstract:
                        value = str(key.abstract)
                        
        except (TypeError, KeyError):
            raise lucidity.error.FormatError(
                'Could not format data {0!r} due to missing key(s) {1!r}.'
                .format(data, list(self.missing(data)))
            )

        else:
            return value

    def keys(self):
        '''Return unique set of placeholders in pattern.'''
        format_specification = self._construct_format_specification(
            self.expanded_pattern()
        )
        if not self.key_resolver:
            return set(self._PLAIN_PLACEHOLDER_REGEX.findall(format_specification))
        else:
            keys = list()
            for key in set(self._PLAIN_PLACEHOLDER_REGEX.findall(format_specification)):
                if key in self.key_resolver:
                    keys.append(self.key_resolver.get(key))
                else:
                    keys.append(key)
            return set(keys)

    def optional_keys(self):
        format_specification = self._construct_format_specification(
            self.expanded_pattern()
        )
        optional_keys = list()
        temp_keys = self._OPTIONAL_KEY_REGEX.findall(format_specification)
        for key in temp_keys:
            optional_keys.extend(self._PLAIN_PLACEHOLDER_REGEX.findall(key))
        if not self.key_resolver:
            return set(optional_keys)
        else:
            keys = list()
            for key in set(optional_keys):
                if key in self.key_resolver:
                    keys.append(self.key_resolver.get(key))
                else:
                    keys.append(key)
            return set(keys)
        

    def references(self):
        '''Return unique set of referenced templates in pattern.'''
        format_specification = self._construct_format_specification(
            self.pattern
        )
        return set(self._TEMPLATE_REFERENCE_REGEX.findall(format_specification))

    def _remove_optional_keys(self, match, data):
        pattern = match.group(0)
        placeholders = list(set(self._PLAIN_PLACEHOLDER_REGEX.findall(pattern)))
        for placeholder in placeholders:
            if not placeholder in data:
                return ""
        return pattern[1:-1]
    
    def _construct_format_specification(self, pattern):
        '''Return format specification from *pattern*.'''
        return self._STRIP_EXPRESSION_REGEX.sub('{\g<1>}', pattern)

    def _construct_expressions(self, pattern):
        optionalKeys = re.split(self._OPTIONAL_KEY_REGEX, pattern)
        options = ['']
        for opt in optionalKeys:
            temp_options = []
            if opt == '':
                continue
            if opt.startswith('['):
                temp_options = options[:]
                opt = opt[1:-1]
            for option in options:
               temp_options.append(option + opt)
            options = temp_options
        return options

    def _construct_regular_expression(self, pattern):
        '''Return a regular expression to represent *pattern*.'''
        # Escape non-placeholder components.
        compiles = list()
        
        expressions = self._construct_expressions(pattern)
        for expression in expressions:
            expression = re.sub(
                r'(?P<placeholder>{(.+?)(:(\\}|.)+?)?})|(?P<other>.+?)',
                self._escape,
                expression
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
                    raise ValueError, message, traceback  #@IgnorePep8
            compiles.append(compiled)
        return compiles

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
        if self.key_resolver:
            if placeholder_name[:-3] in self.key_resolver:
                #check if there is a regex on the key object
                key = self.key_resolver.get(placeholder_name[:-3])
                if key.regex:
                    expression = key.regex.pattern
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
