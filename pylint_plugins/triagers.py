from astroid import MANAGER
from astroid import scoped_nodes

from importlib import import_module

def register(linter):
  pass


def add_dynamic_attr(cls, klass):
    parser = klass.create_parser()
    import argparse
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue

        if isinstance(action, (argparse._StoreTrueAction, argparse._StoreTrueAction)):
            cls.locals[action.dest] = [bool]
        elif isinstance(action, argparse._CountAction):
            cls.locals[action.dest] = [int]
        elif isinstance(action, (argparse._AppendAction, argparse._AppendConstAction)):
            cls.locals[action.dest] = [list]
        else:
            cls.locals[action.dest] = [action.type]


def transform(cls):
    if cls.name in ['AnsibleTriage', 'DefaultTriager', 'SimpleTriager']:
        mod = import_module(cls.parent.name)
        add_dynamic_attr(cls, getattr(mod, cls.name))


MANAGER.register_transform(scoped_nodes.Class, transform)
