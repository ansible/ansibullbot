#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) 2020 Matt Martz <matt@sivel.net>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

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
from functools import lru_cache

from github import Github  # pygithub
from logzero import logger
import ruamel.yaml

import ansibullbot.constants as C
from ansibullbot.utils.component_tools import AnsibleComponentMatcher
from ansibullbot.utils.git_tools import GitRepoWrapper


logging.level = logging.DEBUG
logFormatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
rootLogger = logging.getLogger()
rootLogger.setLevel(logging.DEBUG)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
rootLogger.addHandler(consoleHandler)



PLUGINS_RE = re.compile(r'lib/ansible/(plugins|modules|module_utils)/.*$') #  FIXME, add inventory *scripts* and tests?
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if GITHUB_TOKEN is None:
    GITHUB_TOKEN = C.DEFAULT_GITHUB_TOKEN
assert GITHUB_TOKEN, "GITHUB_TOKEN env var must be set to an oauth token with repo:read from https://github.com/settings/"


def botmeta_list(inlist):
    if not isinstance(inlist, list):
        return inlist
    # can't join words with spaces in them
    if [x for x in inlist if ' ' in x]:
        return inlist
    else:
        return ' '.join(sorted([x.strip() for x in inlist if x.strip()]))


class AnsibleBotmeta:
    def __init__(self):
        self.cachedir = '/tmp/ansibot.cache'
        self.gitrepo = GitRepoWrapper(
            cachedir=self.cachedir,
            repo='https://github.com/ansible/ansible'
        )
        self.component_matcher = AnsibleComponentMatcher(
            gitrepo=self.gitrepo,
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
    _nwo = None
    _flatmap = None

    def __init__(self, g=None, ansibotmeta=None):
        self.g = g
        self.compile()
        self.ansibotmeta = ansibotmeta

    def compile(self):
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
        ''' pretend dicts are lists? '''
        return self._nwo.get(pluginfile)

    def collection_has_subdirs(self, ns):
        return ns in self._flatmaps


def read_ansible_botmeta(ansible_repo=None, nwo=None):

    botmeta_collections = {}

    # Read in botmeta from ansible/ansible
    f = ansible_repo.get_contents(".github/BOTMETA.yml")
    botmeta = yaml.safe_load(base64.b64decode(f.content))
    for key, contents in botmeta['files'].items():

        # Find which Schema contains this file
        match = None
        f = key.replace('$modules', 'lib/ansible/modules')
        f = f.replace('$module_utils', 'lib/ansible/module_utils')
        f = f.replace('$plugins', 'lib/ansible/plugins')
        #if f in nwo:
        import epdb; epdb.st()
        if nwo.find(f):
            # Rewrite path
            # FIXME If community.general, keep module directory structure for modules only
            plugin = f.replace('lib/ansible/modules', 'plugins/modules')
            plugin = plugin.replace('lib/ansible/module_utils', 'plugins/module_utils')
            plugin = plugin.replace('lib/ansible/plugins', 'plugins')
            plugin = plugin.replace('test/integration/targets', 'tests/integration/targets')
            plugin = plugin.replace('test/units', 'tests/units')

            if not nwo[f] in botmeta_collections:
                botmeta_collections[nwo[f]] = {}

            botmeta_collections[nwo[f]][plugin] = contents
          # Remove support
          # Remove migrated_to
          # or do we do this once over the whole data structure?

        else:
            # FIXME Maybe a directory, or regexp?
            # If we expect BOTMETA to have migrated_to for each file, this may not happen for plugins
            # Though may still happen for plugins

            print ("Can't find " + f)
        #else:
            #q.q("'Couldn't find" + f)
            #sys.exit()

    return botmeta_collections


def common_path(paths):
    if len(paths) == 1:
        return paths[0]
    cpaths = OrderedDict()
    for path in paths:
        pparts = path.split('/')
        for ppart in pparts:
            if ppart not in cpaths:
                cpaths[ppart] = 0
            cpaths[ppart] += 1
    for cp,cval in copy.deepcopy(cpaths).items():
        if cval != len(paths):
            cpaths.pop(cp, None) 
    return '/'.join(cpaths.keys()) + '/'


def reduce_collection_botmeta(botmeta):

    nfm = {}
    last_fp = None
    last_fd = None
    fpkeys = sorted(list(botmeta['files'].keys()))
    for fp in fpkeys:
        fd = botmeta['files'][fp]

        if os.path.basename(fp) == '__init__.py':
            continue

        '''
        # do not aggregate empty meta
        if fd is None:
            nfm[fp] = None
            last_fp = None
            last_fd = None
            continue
        '''

        # no matches yet, so reset the stack ...
        if last_fp is None:
            last_fp = [fp]
            last_fd = copy.deepcopy(fd)
            continue

        # another match. save it and continue on ...
        if last_fd == fd:
            last_fp.append(fp)
            logger.info(fp)
            continue

        # this file has new data so dump the stack
        logger.info(last_fp)
        cp = common_path(last_fp)
        if last_fd:
            nfm[cp] = copy.deepcopy(last_fd)
        else:
            nfm[cp] = None

        #if 'netvisor' in last_fp[0] and 'modules' in last_fp[0]:
        #    import epdb; epdb.st()

        # start a new stack
        last_fp = [fp]
        last_fd = copy.deepcopy(fd)

    # don't forget the last one ...
    if last_fp is not None and last_fp[0] not in nfm:
        nfm[last_fp[0]] = last_fd

    # now get rid of subkeys that also come from parents 
    for fp,fd in copy.deepcopy(nfm).items():
        if not fd:
            continue
        for _fp,_fd in copy.deepcopy(nfm).items():
            if fp == _fp:
                continue
            if not _fp.endswith('/'):
                continue
            if fp.startswith(_fp):
                if fd == _fd:
                    nfm.pop(fp, None)
                    continue
                if isinstance(fd, dict) and isinstance(_fd, dict):
                    for key,val in _fd.items():
                        if fd.get(key) == val:
                            nfm[fp].pop(key, None)
                break

    nbm = copy.deepcopy(botmeta)
    nbm['files'] = nfm

    return nbm


def process_aggregated_list_of_files(g, nwo, ansibotmeta):

    # TODO
    #   - missing keywords
    #   - missing teams

    filemacros = OrderedDict([
        ('lib/ansible/module_utils', '$module_utils'),
        ('lib/ansible/modules', '$modules'),
        ('lib/ansible/plugins/action', '$actions'),
        ('lib/ansible/plugins/become', '$becomes'),
        ('lib/ansible/plugins/callback', '$callbacks'),
        ('lib/ansible/plugins/cliconf', '$cliconfs'),
        ('lib/ansible/plugins/connection', '$connections'),
        ('lib/ansible/plugins/doc_fragments', '$doc_fragments'),
        ('lib/ansible/plugins/filter', '$filters'),
        ('lib/ansible/plugins/httpapi', '$httpapis'),
        ('lib/ansible/plugins/inventory', '$inventories'),
        ('lib/ansible/plugins/lookup', '$lookups'),
        ('lib/ansible/plugins/shell', '$shells'),
        ('lib/ansible/plugins/terminal', '$terminals'),
        #('lib/ansible/plugins', '$plugins'),
    ]) 

    topop = [
        'assign',
        'authors',
        'committers',
        'metadata',
        'migrated_to',
        'name',
        'namespace',
        'namespace_maintainers',
        'repo_filename',
        'support',
        'supported_by',
        'subtopic',
        'topic',
    ]

    BOTMETAS = {}

    cdir = '/tmp/nwo.cache'
    if not os.path.exists(cdir):
        os.makedirs(cdir)

    # build the entire list of metadata per collection
    for fn in ansibotmeta.gitrepo.files:
        logger.info(fn)
        cfile = os.path.join(cdir, '%s.json' % fn.replace('/', '_'))
        if os.path.exists(cfile):
            with open(cfile, 'r') as f:
                fmeta = json.loads(f.read())
        else:
            fmeta = ansibotmeta.component_matcher.get_meta_for_file(fn)
            with open(cfile, 'w') as f:
                f.write(json.dumps(fmeta))

        dst = nwo.find(fn)
        if dst and dst != 'ansible._core':
            if dst not in BOTMETAS:
                BOTMETAS[dst] = {
                    'automerge': False,
                    'files': {},
                    'macros': {}
                }
            BOTMETAS[dst]['files'][fn] = copy.deepcopy(fmeta)

    # clean up entries
    for collection, cdata in BOTMETAS.items():
        for fn,fmeta in cdata['files'].items():
            nmeta = copy.deepcopy(fmeta)

            '''
            # keywords didn't bubble up through the bot
            keywords = ansibotmeta.get_keywords(fn)
            if keywords:
                nmeta['keywords'] = keywords[:]
            '''
            
            # is each ignored person even on the list?
            if nmeta.get('ignore'): 
                for user in nmeta['ignore']:
                    found = False
                    for key in ['assign', 'authors', 'maintainers', 'notify', 'namespace_maintainers']:
                        if key in nmeta and user in nmeta[key]:
                            found = True
                            break
                    if not found:
                        nmeta['ignore'].remove(user)

            # dedupe notify and maintainers
            for user in nmeta['notify'][:]:
                if user in nmeta['maintainers']:
                    nmeta['notify'].remove(user)

            # let maintainers be implicit from authors
            if fmeta.get('authors'):
                for author in fmeta['authors']:
                    for key in ['assign', 'maintainers', 'notify', 'namespace_maintainers']:
                        if author in nmeta[key]:
                            nmeta[key].remove(author)

            # remove keys not suitable for botmeta
            for key in topop:
                nmeta.pop(key, None)

            # add explicit labels from botmeta
            labels = ansibotmeta.get_labels(fn)
            if labels:
                for x in labels:
                    if x not in nmeta['labels']:
                        nmeta['labels'].append(x)

            # remove labels that are part of the path
            pparts = fn.split('/')
            for label in nmeta['labels'][:]:
                if label in pparts:
                    nmeta['labels'].remove(label)

            # remove keys with empty or Nonetype values
            for k,v in copy.deepcopy(nmeta).items():
                if not v:
                    nmeta.pop(k, None)

            # insert teams
            for key in ['maintainers', 'notify']:
                if key in nmeta:
                    names = ansibotmeta.names_to_teams(nmeta[key])
                    if names != nmeta[key]:
                        nmeta[key] = names
                        for name in names:
                            if name.startswith('$team'):
                                team = ansibotmeta.get_team(name)
                                BOTMETAS[collection]['macros'][name.lstrip('$')] = team[:]

            # make stringy lists
            for k,v in copy.deepcopy(nmeta).items():
                nmeta[k] = botmeta_list(v)

            # use new meta or just an empty string
            if nmeta:
                BOTMETAS[collection]['files'][fn] = nmeta
            else:
                BOTMETAS[collection]['files'][fn] = None

    # make stringy lists for all the teams
    for collection, cdata in BOTMETAS.items():
        for macro,vals in cdata['macros'].items():
            if not macro.startswith('team'):
                continue
            BOTMETAS[collection]['macros'][macro] = botmeta_list(vals)

    # if maintainers is the only key, make it the entire value
    for collection, cdata in BOTMETAS.items():
        for fp,fd in cdata['files'].items():
            if fd and list(fd.keys()) == ['maintainers']:
                BOTMETAS[collection]['files'][fp] = fd['maintainers']

    # switch filepaths to macros
    for collection, cdata in BOTMETAS.items():
        has_subdirs = nwo.collection_has_subdirs(collection)
        for fn,fmeta in copy.deepcopy(cdata['files']).items():
            nk = fn
            for fp, macro in filemacros.items():
                if fn.startswith(fp):
                    BOTMETAS[collection]['macros'][macro] = 'plugins/%s' % os.path.basename(fp)
                    if has_subdirs and 'module' in fn:
                        nk = nk.replace(fp, macro)
                    else:
                        nk = os.path.join(macro, os.path.basename(fn))
            BOTMETAS[collection]['files'][nk] = copy.deepcopy(fmeta)
            BOTMETAS[collection]['files'].pop(fn, None)
        # sort the macro keys
        mkeys = sorted(list(BOTMETAS[collection]['macros'].keys()))
        for mkey in mkeys:
            mval = BOTMETAS[collection]['macros'][mkey]
            BOTMETAS[collection]['macros'].pop(mkey, None)
            BOTMETAS[collection]['macros'][mkey.lstrip('$')] = mval

    # reduce each file 
    for collection, cdata in BOTMETAS.items():
        BOTMETAS[collection] = reduce_collection_botmeta(cdata)

    ddir = '/tmp/botmeta'
    if os.path.exists(ddir):
        shutil.rmtree(ddir)
    os.makedirs(ddir)

    for collection,cdata in BOTMETAS.items():
        fn = os.path.join(ddir, '%s.yml' % collection)
        with open(fn, 'w') as f:
            ruamel.yaml.dump(cdata, f, width=4096, Dumper=ruamel.yaml.RoundTripDumper)



def main():
    logger.info('instantiate github')
    g = Github(GITHUB_TOKEN)
    logger.info('instantiate nwoinfo')
    nwo = NWOInfo(g=g)
    logger.info('instantiate ansibotmeta')
    ansibotmeta = AnsibleBotmeta()
    logger.info('process ...')
    process_aggregated_list_of_files(g, nwo, ansibotmeta)
    sys.exit(0)

    ansible_repo = g.get_repo('ansible/ansible')
    #globs = [p for p in nwo if '*' in p]
    botmeta_collections = read_ansible_botmeta(ansible_repo=ansible_repo, nwo=nwo)


    # FIXME Need to copy team_ macros across

    # For each entry in botmeta
    #   Given module_utils/postgres.py
    #   Find in schema
    #     # Known collection name
              # new_bot_meta{collection}{'files'}{$new_path} = $data

    print (yaml.dump(botmeta_collections))

    sys.exit()

    moves = {}
    for f in ansible.get_contents('changelogs/fragments'):
        for commit in ansible.get_commits(path=f.path):
            files = [p.filename for p in commit.files]
            plugins = [p for p in files if PLUGINS_RE.search(p)]
            if not plugins:
                continue

            match = None
            if plugins[0] in nwo:
                match = plugins[0]
            else:
                try:
                    for glob in globs:
                        for plugin in plugins:
                            if fnmatch.fnmatch(glob, plugin):
                                match = glob
                                raise StopIteration()
                except StopIteration:
                    pass

            if match:
                collection = nwo[match]
                print('%s' % f.path, file=sys.stderr)
                print(
                    '    %s - %s' % (collection, match),
                    file=sys.stderr
                )

                clog_data = yaml.safe_load(base64.b64decode(f.content))
                moves[f.path] = {
                    'collection': collection,
                    'changelog': clog_data,
                }

                break

    print(file=sys.stderr)
    print(json.dumps(moves, sort_keys=True, indent=4))


if __name__ == "__main__":
    main()
