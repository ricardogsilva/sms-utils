#!/usr/bin/env python
# -*- coding: utf-8 -*-


'''
Tools for parsing and writing for SMS definition files.

The ultimate goal of this project is to create a django application
that provides a GUI for creating and editing SMS suites.

The application will be able to:
    - read existing definition files and generate the corresponding suite
    - read existing json files and generate the corresponding sms elements
    - create suites from scratch
    - add/remove families/tasks/triggers/... from suites
    - save suites in the database
    - export suites in:
        - .def file format
        - json format


TODO:
    - Refactor the code with better inheritance modelling
    - Add parsing rules for comments
    - Add a save() method to Suite objects to save their cdp definiton to a file
    - Add a from_json() method to construct SMSNode objects from JSON
    - Convert this code to a django application.
    - Build a GUI with JQuery and JsTree

Suite
    - name, sms_type, to_json, cdp_definition
    - parent, path
    - has variables, families
Family
    - name, sms_type, to_json, cdp_definition
    - parent, path
    - has variables, families, tasks, labels(?), trigger, meters(?)
Task
    - name, sms_type, to_json, cdp_definition
    - parent, path
    - has variables, trigger, labels, meters
Meter
    - name, sms_type, to_json, cdp_definition
    - parent, path
Label
    - name, sms_type, to_json, cdp_definition
    - parent, path
'''

import re
import json
import copy
import pyparsing as pp

# TODO
# add the remaining SMS elements (trigger)
def to_json(obj):
    '''
    Serialize the SMS element classes to JSON.
    '''

    if isinstance(obj, Task):
        result = {
            'sms_type' : obj.sms_type,
            'name' : obj.name,
            'variables' : obj.variables,
            'labels' : obj.labels,
            'meters' : obj.meters,
        }
    elif isinstance(obj, Family):
        result = {
            'sms_type' : obj.sms_type,
            'name' : obj.name,
            'variables' : obj.variables,
            'tasks' : obj.tasks,
            'families' : obj.families,
        }
    elif isinstance(obj, Suite):
        result = {
            'sms_type' : obj.sms_type,
            'name' : obj.name,
            'variables' : obj.variables,
            'families' : obj.families,
        }
    elif isinstance(obj, Label):
        result = {
            'sms_type' : obj.sms_type,
            'name' : obj.name,
            'text' : obj.text,
        }
    elif isinstance(obj, Meter):
        result = {
            'sms_type' : obj.sms_type,
            'name' : obj.name,
            'minimum' : obj.minimum,
            'maximum' : obj.maximum,
            'mark' : obj.mark,
        }
    else:
        raise TypeError(repr(obj) + 'is not JSON serializable')
    return result

def sms_grammar():
    quote = pp.Word('"\'', exact=1).suppress()
    colon = pp.Literal(':').suppress()
    l_paren = pp.Literal('(').suppress()
    r_paren = pp.Literal(')').suppress()
    sms_node_path = pp.Word('./_' + pp.alphanums)
    identifier = pp.Word(pp.alphas, pp.alphanums + '_')
    var_value = pp.Word(pp.alphanums) | (quote + \
            pp.Combine(pp.OneOrMore(pp.Word(pp.alphanums)), adjacent=False, 
                       joinString=' ') + quote)
    sms_var = pp.Group(pp.Keyword('edit') + identifier + var_value)
    sms_label = pp.Group(pp.Keyword('label') + identifier + var_value)
    sms_meter = pp.Group(pp.Keyword('meter') + identifier + pp.Word(pp.nums) * 3)
    sms_limit = pp.Group(pp.Keyword('limit') + identifier + pp.Word(pp.nums))
    sms_in_limit = pp.Group(pp.Keyword('inlimit') + sms_node_path + colon + identifier)
    sms_trigger = pp.Group(pp.Keyword('trigger') + pp.restOfLine)
    sms_task = pp.Group(
        pp.Keyword('task') + \
        identifier + \
        pp.ZeroOrMore(
            sms_trigger ^ sms_in_limit ^ sms_label ^ sms_meter ^ sms_var
        )
    ) + pp.Optional(pp.Keyword('endtask').suppress())
    sms_family = pp.Forward()
    sms_family << pp.Group(
        pp.Keyword('family') + identifier + pp.ZeroOrMore(
            sms_in_limit ^ sms_limit ^ sms_trigger ^ sms_var ^ sms_task ^ sms_family
        )
    ) + pp.Keyword('endfamily').suppress()
    sms_suite = pp.Keyword('suite') + identifier + \
                pp.ZeroOrMore(sms_var ^ sms_family) + \
                pp.Keyword('endsuite').suppress()
    return sms_suite

class SMSNode(object):

    _name = ''
    _parent = None
    _path = ''
    _suite = None
    variables = dict()
    status = 'unknown'
    sms_type = None

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name
        old_path_list = self._path.split('/')
        self._path = '/'.join(old_path_list[:-1]) + '/' + self._name

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
        self.parent = parent
        if parse_obj is not None:
            self.name = parse_obj[1]
            self.variables = self._get_variables(parse_obj)

    def cdp_definition(self, indent_order=0):
        output = '%s%s %s\n' % ('\t'*indent_order, self.sms_type, self.name)
        output += self._start_cdp_definition(indent_order)
        output += self._specific_cdp_definition(indent_order+1)
        output += self._end_cdp_definition(indent_order)
        return output

    def _start_cdp_definition(self, indent_order=0):
        output = ''
        for k, v in self.variables.iteritems():
            output += '%sedit %s "%s"\n' % ('\t'*(indent_order+1), k, v)
        return output

    def _end_cdp_definition(self, indent_order=0):
        output = '%send%s\n' % ('\t'*indent_order, self.sms_type)
        return output

    def _specific_cdp_definition(self, indent_order=0):
        return ''

    def _get_variables(self, parse_obj):
        d = dict()
        for v in [var for var in parse_obj if var[0] == 'edit']:
            d[v[1]] = v[2]
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

    def to_json(self, indent=None):
        return json.dumps(self, default=to_json, indent=indent)

    def __repr__(self):
        return self.name

    # TODO - extend with more filtering options
    def filter_nodes(self, node_type=None, node_name=None):
        nodes = []
        nodes_to_iter = []
        if hasattr(self, 'families'): 
            nodes_to_iter += self.families
        if hasattr(self, 'tasks'): 
            nodes_to_iter += self.tasks
        for n in nodes_to_iter:
            conditions = {
                'node_type' : False,
                'node_name' : False,
            }
            for c in conditions.keys():
                value = eval(c)
                if value is None:
                    conditions[c] = True
                else:
                    if c == 'node_type' and n.sms_type == value:
                        conditions[c] = True
                    elif c == 'node_name' and re.search(value, n.name) is not None:
                        conditions[c] = True
            if False not in conditions.values():
                nodes.append(n)
            nodes += n.filter_nodes(node_type, node_name)
        return nodes


class Suite(SMSNode):

    families = []

    def __init__(self, def_file, grammar=None):
        if grammar is None:
            grammar = sms_grammar()
        self.grammar = grammar
        parse_obj = self._parse_file(def_file)
        self.parse_obj = parse_obj
        super(Suite, self).__init__(parse_obj=parse_obj, parent=None)
        self._path = '/'
        self.families = [Family(f, parent=self) for f in parse_obj if f[0] == 'family']
        for f in self.families:
            f._parse_triggers()

    def _parse_file(self, def_file):
        fh = open(def_file, 'r')
        parse_obj = self.grammar.parseString(fh.read())
        return parse_obj

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


class NodeWithTriggers(SMSNode):

    trigger = ('', [])
    _trigger_exp = ''

    def _parse_trigger(self):

        new_exp = ''
        nodes = []
        path_obj = re.compile(r'(\(*)([\w\d./=]*)(\)*)')
        for tok in self._trigger_exp.split():
            re_obj = path_obj.search(tok)
            for i in re_obj.groups():
                if i == '':
                    pass
                elif ('(' in i) or (')' in i):
                    new_exp += i
                elif i in ('complete', 'unknown'):
                    new_exp += ' "%s" ' % i
                elif i in ('AND', 'OR'):
                    new_exp += ' %s ' % i.lower()
                elif i in ('==',):
                    new_exp += ' %s ' % i
                else:
                    new_exp += ' "%s" '
                    nodes.append(self.get_node(i))
        self.trigger = new_exp, nodes

    def evalute_trigger(self):
        exp, nodes = self.trigger
        if exp == '':
            result = True
        else:
            result = eval(exp % tuple([n.status for n in nodes]))
        return result


class Task(NodeWithTriggers):

    in_limits = []
    meters = []
    labels = []

    def __init__(self, parse_obj=None, parent=None, name=None, 
                 variables=None, trigger=None, meters=None):
        if parse_obj is None and name is None:
            raise Exception
        else:
            super(Task, self).__init__(parse_obj=parse_obj, parent=parent)
            if parse_obj is not None:
                self._parse_cdp(parse_obj)
            if name is not None:
                self.name = name
            if variables is not None:
                self.variables.update(variables)
            if trigger is not None:
                self.trigger = trigger
            if meters is not None:
                self.meters = meters

    def _parse_cdp(self, parse_obj):
        self.meters = [Meter(m[1], m[2], m[3], m[4], self) for m in parse_obj if m[0] == 'meter']
        self.labels = [Label(la[1], la[2], self) for la in parse_obj if la[0] == 'label']
        try:
            self._trigger_exp = [t[1] for t in parse_obj if t[0] == 'trigger'][0]
        except IndexError:
            pass

    def add_label(self, label):
        if label not in self.labels:
            self.labels.append(label)
            label.parent = self

    def remove_label(self, label):
        self.labels.remove(label)
        label.parent = None

    def add_meter(self, meter):
        if meter not in self.meters:
            self.meters.append(meter)
            meter.parent = self

    def remove_meter(self, meter):
        self.meters.remove(meter)
        meter.parent = None

    def _node_from_path(self, path):
        node = None
        if path == self.path or path == '':
            node = self
        return node

    def _specific_cdp_definition(self, indent_order=0):
        output = ''
        exp, nodes = self.trigger
        if exp != '':
            trig = exp % tuple([n.path for n in nodes])
            output += '%strigger %s\n' % ('\t' * indent_order, trig)
        return output


class Family(NodeWithTriggers):

    families = []
    tasks = []
    limits = dict()
    in_limits = []

    def __init__(self, parse_obj=None, parent=None, name=None):
        if parse_obj is None and name is None:
            raise Exception
        super(Family, self).__init__(parse_obj=parse_obj, parent=parent)
        if parse_obj is None:
            self.name = name
        else:
            self.families = [Family(f, parent=self) for f in parse_obj if f[0] == 'family']
            self.tasks = [Task(t, parent=self) for t in parse_obj if t[0] == 'task']
            self._parse_limits(parse_obj)
            self._parse_in_limits(parse_obj)
            try:
                self._trigger_exp = [t[1] for t in parse_obj if t[0] == 'trigger'][0]
            except IndexError:
                pass

    def _parse_triggers(self):
        self._parse_trigger()
        for t in self.tasks:
            t._parse_trigger()
        for f in self.families:
            f._parse_triggers()

    def _parse_limits(self, parse_obj):
        self.limits = dict()
        for lim in [lim for lim in parse_obj if lim[0] == 'limit']:
            self.limits[lim[1]] = lim[2]

    # FIXME - untested
    def _parse_in_limits(self, parse_obj):
        self.in_limits = []
        for inlim in [il for il in parse_obj if il[0] == 'inlimit']:
            node = self.get_node(inlim[1])
            limit = node.limits.get(inlim[2], None)
            self.in_limits.append((node, limit))

    # TODO:
    # - add trigger definition
    def _specific_cdp_definition(self, indent_order=0):
        output = ''
        for n in self.tasks + self.families:
            output += n.cdp_definition(indent_order)
        return output

    def _start_cdp_definition(self, indent_order=0):
        output = ''
        for name, num in self.limits.iteritems():
            output += '%slimit %s %s\n' % ('\t'*(indent_order+1), name, num)
        output += super(Family, self)._start_cdp_definition(indent_order)
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

    def add_task(self, task):
        if task not in self.tasks:
            if task.parent is not None:
                task.parent.remove_task(task)
            self.tasks.append(task)
            task.parent = self

    def remove_task(self, task):
        self.tasks.remove(task)
        task.parent = None


class ExtraNode(object):

    _name = ''
    _parent = None
    _path = ''
    sms_type = None

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, the_name):
        self._name = the_name
        self._path = self._path.rpartition(':')[0] + ':' + self._name

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, parent):
        if isinstance(parent, Task):
            self._parent = parent
            self._path = parent.path + ':' + self.name

    @property
    def path(self):
        return self._path

    def __init__(self, name, parent=None):
        self.name = name
        self.parent = parent
        self.sms_type = self.__class__.__name__.lower()

    def __repr__(self):
        return self.name



class Meter(ExtraNode):

    _minimum = 0
    _maximum = 100
    _mark = 100

    @property
    def minimum(self):
        return self._minimum

    @property
    def maximum(self):
        return self._maximum

    @property
    def mark(self):
        return self._mark

    @mark.setter
    def mark(self, value):
        if self._minimum <= value <= self._maximum:
            self._mark = value
        else:
            pass

    def __init__(self, name, the_min=None, the_max=None, the_mark=None, 
                 parent=None):
        super(Meter, self).__init__(name, parent)
        if the_min is not None:
            self._minimum = int(the_min)
        if the_max is not None:
            self._maximum = int(the_max)
        if the_mark is not None:
            self.mark = int(the_mark)


class Label(ExtraNode):

    text = ''

    def __init__(self, name, text=None, parent=None):
        super(Label, self).__init__(name, parent)
        if text is not None:
            self.text = text

    def __repr__(self):
        return self.name
