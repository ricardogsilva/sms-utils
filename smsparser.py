#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
Tools for parsing and writing for SMS definition files.

TODO:
    - Add parsing rules for: trigger, limit, label, meter
    - Add a data model for the missing SMS objects (limit, label, meter)
    - Add a save() method to Suite objects to save their cdp definiton to a file
    - Add a serialize() method to SMSNode objects that serializes to JSON
    - Add a deserialize() method to construct SMSNode objects from JSON
    - Restrict the Suite class so that:
        - parent cannot be changed
    - Restrict the Family class so that:
        - parent cannot be set to an instance of Task

'''

import pyparsing as pp

class SMSNode(object):

    _name = ''
    _parent = None
    _path = ''
    _suite = None
    variables = dict()
    status = 'unknown'

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name
        self.parent = self.parent

    @property
    def path(self):
        return self._path

    @property
    def suite(self):
        return self._suite

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, parent):
        self._parent = parent
        if self._parent is None:
            self._path = self.name
        else:
            if self._parent.path == '/':
                self._path = self._parent.path + self.name
            else:
                self._path = self._parent.path + '/' + self.name
        self._suite = self.get_suite()

    def __init__(self, parse_obj=None, parent=None):
        self.sms_type = self.__class__.__name__.lower()
        self._parent = parent
        if parse_obj is not None:
            self.name = parse_obj.name
            self.variables = self._get_variables(parse_obj)
        else:
            pass

    def cdp_definition(self, indent_order=0):
        output = '%s%s %s\n' % ('\t'*indent_order, self.sms_type, self.name)
        output = self._start_cdp_definition(indent_order)
        output += self._specific_cdp_definition(indent_order+1)
        output += self._end_cdp_definition(indent_order)
        return output

    def _start_cdp_definition(self, indent_order=0):
        output = '%s%s %s\n' % ('\t'*indent_order, self.sms_type, self.name)
        for k, v in self.variables.iteritems():
            output += '%sedit %s "%s"\n' % ('\t'*(indent_order+1), k, v)
        return output

    def _end_cdp_definition(self, indent_order=0):
        output = '%send%s\n' % ('\t'*indent_order, self.sms_type)
        return output

    def _specific_cdp_definition(self, indent_order=0):
        return ''

    def _get_variables(self, parseObj):
        d = dict()
        for v in parseObj.variables.keys():
            d[v] = parseObj.variables.__getattr__(v)
        return d

    def get_suite(self):
        if self._parent is None:
            result = None
        else:
            result = self._parent.get_suite()
        return result

    def get_node(self, path):
        '''
        Return the node with the defined path.

        Paths can be given in an absolute or relative way.

        Inputs:

            path - a path to another node on the suite
        '''

        if path.startswith('/'):
            base_node = self.get_suite()
            node = base_node.get_node(path[1:])
        else:
            base_node = self.parent
            if base_node is None:
                base_node = self.get_suite()
            path_list = path.split('/')
            rel_path_list = []
            for token in path_list:
                if token == '..':
                    base_node = base_node.parent
                else:
                    rel_path_list.append(token)
            rel_path = '/'.join(rel_path_list)
            node = None
            if base_node is not None:
                node = base_node._node_from_path(rel_path)
        return node

    def __repr__(self):
        return self.name


class Suite(SMSNode):

    families = []

    def __init__(self, def_file, grammar=None):
        if grammar is None:
            grammar = self._get_default_grammar()
        self.grammar = grammar
        parse_obj = self._parse_file(def_file)
        self.parse_obj = parse_obj
        super(Suite, self).__init__(parse_obj=parse_obj, parent=None)
        self._path = '/'
        self.families = [Family(f, parent=self) for f in parse_obj.families]
        #for f in self.families:
        #    f._parse_triggers()

    def _parse_file(self, def_file):
        fh = open(def_file, 'r')
        parse_obj = self.grammar.parseString(fh.read())
        return parse_obj

    def _get_default_grammar(self):
        quote = pp.Word('\'"', exact=1).suppress()
        l_paren = pp.Literal('(').suppress()
        r_paren = pp.Literal(')').suppress()
        identifier = pp.Word(pp.alphas, pp.alphanums)
        var_start = pp.Keyword('edit').suppress()
        task_start = pp.Keyword('task').suppress()
        task_end = pp.Keyword('endtask').suppress()
        family_start = pp.Keyword('family').suppress()
        family_end = pp.Keyword('endfamily').suppress()
        suite_start = pp.Keyword('suite').suppress()
        suite_end = pp.Keyword('endsuite').suppress()
        status_complete = pp.Keyword('complete')
        sms_node_path = pp.Word('./' + pp.alphanums)
        trigger_eq = pp.Keyword('==')
        trigger_neq = pp.Keyword('!=')
        trigger_start = pp.Keyword('trigger').suppress()
        trigger_and = pp.Keyword('AND')
        trigger_or = pp.Keyword('OR')
        #trigger_exp = pp.Forward()
        trigger_exp = pp.Group(sms_node_path + (trigger_eq ^ trigger_neq) + \
                status_complete)
        boolean_relation = pp.Forward()
        boolean_relation << pp.Group(pp.Optional(l_paren) + trigger_exp + \
                pp.ZeroOrMore((trigger_and ^ trigger_or) + boolean_relation) + \
                pp.Optional(r_paren))
        #trigger_value = trigger_start + pp.Group(trigger_exp) 
        trigger_value = trigger_start + pp.Group(boolean_relation)

        var_value = pp.Word(pp.alphanums) | (quote + pp.Combine(pp.OneOrMore(pp.Word(pp.alphanums)), adjacent=False, joinString=' ') + quote)
        sms_var = var_start + pp.Dict(pp.Group(identifier + var_value))
        sms_task = task_start + \
                   pp.Dict(
                        pp.Group(
                            identifier.setResultsName('name') + \
                            pp.Group(pp.ZeroOrMore(trigger_value)).setResultsName('triggers') & \
                            pp.Group(pp.ZeroOrMore(sms_var)).setResultsName('variables')
                        ) \
                    ) + pp.Optional(task_end)
        sms_family = pp.Forward()
        sms_family << family_start + \
                pp.Dict(
                        pp.Group(
                            identifier.setResultsName('name') + \
                            pp.Group(pp.ZeroOrMore(sms_var)).setResultsName('variables') & \
                            pp.Group(pp.ZeroOrMore(sms_task)).setResultsName('tasks') & \
                            pp.Group(pp.ZeroOrMore(sms_family)).setResultsName('families') \
                        )
                ) + family_end
        sms_suite = suite_start + identifier.setResultsName('name') + \
                    pp.Group(pp.ZeroOrMore(sms_var)).setResultsName('variables') & \
                    pp.Group(pp.ZeroOrMore(sms_family)).setResultsName('families') \
                    + suite_end
        return sms_suite

    def _specific_cdp_definition(self, indent_order=0):
        output = ''
        for n in self.families:
            output += n.cdp_definition(indent_order)
        return output

    def _node_from_path(self, path):
        if path == '' or path == '.':
            node = self
        else:
            path_list = path.split('/')
            node_list = self.families
            possible_node = None
            for n in node_list:
                if n.name == path_list[0]:
                    new_path = '/'.join(path_list[1:])
                    possible_node = n._node_from_path(new_path)
            node = possible_node
        return node

    def get_suite(self):
        return self


class Task(SMSNode):

    triggers = []
    _trigger_exps = []

    def __init__(self, parse_obj=None, parent=None, name=None, 
                 variables=None, triggers=None):
        if parse_obj is None and name is None:
            raise Exception
        super(Task, self).__init__(parse_obj=parse_obj, parent=parent)
        self.triggers = []
        self._trigger_exps = [t for t in parse_obj.triggers]
        if name is not None:
            self.name = name
        if variables is not None:
            self.variables.update(variables)

    def _node_from_path(self, path):
        node = None
        if path == self.path or path == '':
            node = self
        return node

    def _parse_triggers(self):
        '''
        Inputs:

            exp - a three element list containing left operand, operator
                and right operand.
        '''

        for exp in self._trigger_exps:
            l_path, operator, status = exp
            l_node = self.get_node(l_path)
            result = None
            if l_node is not None:
                self.triggers.append([l_node, operator, status])


    def _specific_cdp_definition(self, indent_order=0):
        output = ''
        for t in self.triggers:
            path, op, st = t[0].path, t[1], t[2] 
            output += '%strigger %s %s %s\n' % ('\t' * indent_order, path, op, st)
        return output


class Family(SMSNode):

    families = []
    tasks = []
    triggers = []

    def __init__(self, parse_obj=None, parent=None, name=None):
        if parse_obj is None and name is None:
            raise Exception
        super(Family, self).__init__(parse_obj=parse_obj, parent=parent)
        if parse_obj is None:
            self.name = name
        else:
            self.families = [Family(f, parent=self) for f in parse_obj.families]
            self.tasks = [Task(t, parent=self) for t in parse_obj.tasks]

    def _parse_triggers(self):
        for n in self.tasks + self.families:
            n._parse_triggers()

    def _specific_cdp_definition(self, indent_order=0):
        output = ''
        for n in self.tasks + self.families:
            output += n.cdp_definition(indent_order)
        return output

    def _node_from_path(self, path):
        if path == '' or path == '.':
            node = self
        else:
            path_list = path.split('/')
            node_list = self.tasks + self.families
            possible_node = None
            for n in node_list:
                if n.name == path_list[0]:
                    new_path = '/'.join(path_list[1:])
                    possible_node = n._node_from_path(new_path)
            node = possible_node
        return node

    #def add_task(self, task_obj):
    #    if task_obj not in self.tasks:
    #        self.tasks.append(task_obj)
    #        task_obj.parent = self
    #        task_obj._update_path(self)


def main(defFile):
    suite = Suite(defFile)

if __name__ == '__main__':
    import sys
    main(sys.argv[1])
    
    
