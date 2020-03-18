#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# generate_collections_doclist.py - make a csv for new file locations
#
# DESCRIPTION:
# 
# USAGE:
#   PYTHONPATH=. ./scripts/generate_collections_doclist.py
#

import base64
import copy
import fnmatch
import json
import logging
import os
import re
import shutil
import sys

import q
import yaml  # pyyaml

from collections import OrderedDict
from collections import defaultdict
from pprint import pprint
from functools import lru_cache

from github import Github  # pygithub
from logzero import logger

import ansibullbot.constants as C
from ansibullbot.utils.component_tools import AnsibleComponentMatcher
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.logs import set_logger
from ansibullbot.utils.galaxy import GalaxyQueryTool

set_logger(debug=True)


GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if GITHUB_TOKEN is None:
    GITHUB_TOKEN = C.DEFAULT_GITHUB_TOKEN
assert GITHUB_TOKEN, "GITHUB_TOKEN env var must be set to an oauth token with repo:read from https://github.com/settings/"




class AnsibotShim:
    '''A shim wrapper for ansibot's builtin functions'''
    def __init__(self):
        self.cachedir = '/tmp/ansibot.cache'
        self.gitrepo = GitRepoWrapper(
            cachedir=self.cachedir,
            repo='https://github.com/ansible/ansible',
            commit='a76d78f6919f62698341be2f102297a2ce30897c'
        )
        self.component_matcher = AnsibleComponentMatcher(
            usecache=True,
            gitrepo=self.gitrepo,
            cachedir='/tmp/ansibot.cache.components',
            email_cache={}
        )

    def get_keywords(self, filename):
        fdata = self.component_matcher.BOTMETA['files'].get(filename, {})
        return fdata.get('keywords', [])

    def get_labels(self, filename):
        fdata = self.component_matcher.BOTMETA['files'].get(filename, {})
        return fdata.get('labels', [])

    def get_team(self, teamname):
        if teamname.startswith('$'):
            teamname = teamname.lstrip('$')
        return self.component_matcher.BOTMETA['macros'].get(teamname, [])

    def names_to_teams(self, namelist):
        # self.component_matcher.BOTMETA['macros']
        match_counts = {}
        for macro,mnames in self.component_matcher.BOTMETA['macros'].items():
            if not macro.startswith('team_'):
                continue
            
            result = all(x in namelist for x in mnames)
            if not result:
                continue

            if macro not in match_counts:
                match_counts[macro] = 0
            for name in namelist:
                if name in mnames:
                    match_counts[macro] += 1

        if not match_counts:
            return namelist

        ranked = sorted(match_counts.items(), key=lambda x: x[1], reverse=True)
        this_team = ranked[0][0]
        this_team_members = self.component_matcher.BOTMETA['macros'][this_team]
        for idx,x in enumerate(namelist):
            if x in this_team_members:
                namelist[idx] = '$%s' % this_team
        namelist = sorted(set(namelist))
        #import epdb; epdb.st()
        return namelist


class NWOInfo:

    '''NWO scenario helper'''

    _nwo = None
    _flatmap = None

    def __init__(self, g=None, ansibotmeta=None):
        self.g = g
        self.compile()
        self.ansibotmeta = ansibotmeta

    def compile(self):
        '''build an internal mapping of all nwo meta'''
        migration_repo = self.g.get_repo('ansible-community/collection_migration')
        ansible_repo = self.g.get_repo('ansible/ansible')

        self._nwo = {}
        self._flatmaps = set()

        # Read in migration scenarios
        for f in migration_repo.get_contents('scenarios/nwo'):
            data = yaml.safe_load(base64.b64decode(f.content))
            namespace, ext = os.path.splitext(f.name)
            if ext != '.yml':
                continue
            for collection, content in data.items():
                name = '%s.%s' % (namespace, collection)
                if content.get('_options', {}).get('flatmap'):
                    self._flatmaps.add(name)
                for ptype, paths in content.items():
                    for relpath in paths:
                        if ptype in ('modules', 'module_utils'):
                            path = 'lib/ansible/%s/%s' % (ptype, relpath)
                        else:
                            path = 'lib/ansible/plugins/%s/%s' % (ptype, relpath)
                        self._nwo[path] = name

    def find(self, pluginfile):
        if pluginfile in self._nwo:
            return self._nwo.get(pluginfile)
        pparts = pluginfile.split('/')
        for k,v in self._nwo.items():
            if '*' not in k:
                continue
            kparts = k.split('/')
            if len(kparts) != len(pparts):
                continue
            z = [x for x in enumerate(kparts) if x[1] in [pparts[x[0]], '*']]
            if len(z) == len(pparts):
                return v
        return None

    def collection_has_subdirs(self, ns):
        '''was the collection flatmapped?'''
        return ns in self._flatmaps


def create_master_file_list(ansibot, nwo, gqt):

    '''Create botmeta for all known collections'''

    rows = []

    cdir = '/tmp/nwo.cache'
    if not os.path.exists(cdir):
        os.makedirs(cdir)

    # build the entire list of metadata per collection
    for fn in ansibot.gitrepo.files:
        if not fn.startswith('lib/ansible/modules'):
            continue
        if os.path.basename(fn) == '__init__.py':
            continue

        logging.info(fn)
        nres = nwo.find(fn)
        gres = gqt.find(os.path.basename(fn))
        bmeta = ansibot.component_matcher.get_meta_for_file(fn)

        if nres == 'ansible._core':
            rows.append([fn, nres, 'base'])
            continue

        if not nres and not gres and not bmeta.get('migrated_to'):
            rows.append([fn, None, 'missing'])

        if bmeta.get('migrated_to'):
            mt = bmeta['migrated_to'][0]
            if mt in [x['collection'] for x in gres]:
                rows.append([fn, mt, 'galaxy'])
            elif mt == nres:
                rows.append([fn, mt, 'TBD:nwo'])
            else:
                rows.append([fn, mt, 'TBD:unknown'])
            continue

        if gres or nres:
            pprint(gres)
            pprint(nres)

            if nres and gres:
                if nres in [x['collection'] for x in gres]:
                    rows.append([fn, nres, 'galaxy'])
                else:
                    matched = False
                    for gr in gres:
                        if gr['score'] == 100:
                            rows.append([fn, gr['collection'], 'galaxy'])
                            matched = True
                            break
                    if not matched:
                        rows.append([fn, nres, 'TBD:nwo'])
            elif nres:
                rows.append([fn, nres, 'TBD:nwo'])

    with open('/tmp/doclist.txt', 'w') as f:
        for row in rows:
            f.write(' '.join([str(x) for x in row]) + '\n')


def main():
    logger.info('instantiate github')
    g = Github(GITHUB_TOKEN)
    logger.info('instantiate nwoinfo')
    nwo = NWOInfo(g=g)
    logger.info('instantiate ansibot')
    ansibot = AnsibotShim()
    gqt = GalaxyQueryTool(cachedir='/tmp/gqt.cache')
    gqt.find('modules/net_ping.py')

    create_master_file_list(ansibot, nwo, gqt)



if __name__ == "__main__":
    main()
