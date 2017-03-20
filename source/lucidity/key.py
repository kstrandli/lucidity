# :coding: utf-8
import re
import logging

class Key(object):
    '''Key baseClass
    used to store and validate values for templates
    a dict needs to be provided
    {'name': 'shot',
    'regex': r'^([0-9]){3}$',
    'type': int,
    'padding': '%04d'
    }
    name and type are the main keys that need to be provided
    without them the object cannot initialize
    types are "str" and "int"
    
    '''
    def __init__(self, name, type,**kwargs):
        super(Key, self).__init__()
        
        self.__name = name
        self.__type = type
        self.__value = None
        self.__regex = None
        self.__padding = None
        self.__function = None
        self.__abstract = ''
        self.__dbEntity = self.__name
        self.__dbField = ''
        
        for key, value in kwargs.items():
            if key == 'regex':
                self.__regex = re.compile(value)
            if key == 'abstract':
                self.__abstract = value
            if key == 'function':
                self.__function = value
                self.__value = value() #call the function once at init to set a value
            if key == 'padding':
                if re.match(r'(\%)([0-9]{0,2})(d)', value):
                    self.__padding = value
                else:
                    raise Exception('provided padding {0} is not a valid padding pattern must be like "%04d"'.format(value))
            if key == 'dbEntity':
                self.__dbEntity = value
            if key == 'dbField':
                self.__dbField = value

    @property
    def name(self):
        return self.__name

    @property
    def type(self):
        return self.__type
    
    @property
    def abstract(self):
        return self.__abstract
    
    @property
    def function(self):
        return self.__function
    
    @property
    def padding(self):
        return self.__padding
    
    @property
    def regex(self):
        return self.__regex
    
    @property
    def dbEntity(self):
        return self.__dbEntity
    
    @property
    def dbField(self):
        return self.__dbField
    
    @property
    def value(self):
        return self.__value

    def setValue(self, value):
        if value:
            if self.type == int and isinstance(value,int) and self.padding:
                ## we can skip the regex check if the incoming value is an int and we do have a padding
                self.__value = self.type(value)
                return
            
            if self.regex:
                if re.match(self.regex, value):
                    if self.abstract:
                        if value == self.abstract:
                            return
                    self.__value = self.type(value)
                    return
                elif str(value) == str(self.name):
                    self.__value = value
                    return
                else:
                    raise Exception('provided value {0} does not match regex {1} for {2}'.format(value, self.regex.pattern,self.__repr__()))
            else:
                self.__value = self.type(value)
                return
            
    def __repr__(self):
        if self.value:
            return  '<lucidity.Key "{0}" value "{1}">'.format(self.name,str(self))
        else:
            return  '<lucidity.Key "{0}">'.format(self.name)
    
    def __str__(self):
        '''
        used in the format method to fill the keys
        '''
        if not self.value and not self.value == 0:
            if self.abstract:
                return str(self.abstract)
            return str(self.name) 
        if self.type == str:
            return str(self.value)
        elif self.type == int and self.padding:
            return self.padding % self.value
        elif self.type == int:
            return str(self.value)
        elif self.function:
            self.__value = self.function()
            return str(self.value)
         
    def __cmp__(self,other):
        '''
        compare against name 
        '''
        return cmp(self.name,other)
    