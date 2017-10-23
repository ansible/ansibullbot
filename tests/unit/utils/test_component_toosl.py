#!/usr/bin/env python

from unittest import TestCase

from ansibullbot.utils.component_tools import ComponentMatcher


class FakeIndexer(object):
    CMAP = {}
    botmeta = {'files': {}}
    modules = {}
    files = []


class TestComponentMatcher(TestCase):

    def test_reduce_filepaths(self):

        MI = FakeIndexer()
        FI = FakeIndexer()

        CM = ComponentMatcher(None, FI, MI)
        filepaths = ['commands/command.py', 'lib/ansible/modules/commands/command.py']
        reduced = CM.reduce_filepaths(filepaths)
        self.assertEqual(reduced, ['lib/ansible/modules/commands/command.py'])
