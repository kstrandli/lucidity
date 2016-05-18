# :coding: utf-8
# :copyright: Copyright (c) 2013 Martin Pengelly-Phillips
# :license: See LICENSE.txt.

import os
import operator
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..','..', 'source'))

import pytest

import lucidity

TEST_TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'fixture', 'template'
) 
from lucidity import Template
from lucidity import key as TemplateKeys

@pytest.fixture(scope='session')
def keys():
    '''Register templates.'''    
 
    keys = [
            {'name': 'ver',
                    'regex': r'([0-9]){3}',
                    'type': int,
                    'padding': '%03d'
                    }
            ,
            {'name': 'asset',
                    'regex': r'[a-zA-Z]*',
                    'type': str,
                    }
            ,
            {'name': 'frame',
                    'regex': r'([0-9]+|%[0-9]+[di]|[#@?]+)',
                    'type': int,
                    'abstract': '%04d',
                    'padding': '%04d'
                    }
            ]
    keyResolver = dict()
    for key in keys:
        keyResolver[key.get('name')]= TemplateKeys.Key(**key)
    return keyResolver


@pytest.mark.parametrize(('name','type'), [
    ('version', int),
    ('asset', str)
], ids=[
    'int key',
    'string key'
])
def test_key(name, type):
    '''Construct Key Objects'''
    TemplateKeys.Key(**locals())
    
    
@pytest.mark.parametrize(('keyName', 'input','expected'), [
    ('ver', None , 'ver'),
    ('ver', 3 , '003'),
    ('asset', 'test', 'test'),
    ('frame', 1, '0001'),
    ('frame', 50, '0050'),
    ('frame', 15550, '15550')
], ids=[
    'version key no value',
    'version padding',
    'string key test',
    'frame 0001',
    'frame 0050',
    'frame 15550'
])
def test_padding(keyName, input, expected, keys):
    key = keys[keyName]
    key.setValue(input)
    assert str(key) == expected
