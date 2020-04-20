#!/usr/bin/env python

import copy
import datetime
import json
import logging
import os
import re
import tarfile
import zipfile

import yaml
import requests

from github import Github

import ansibullbot.constants as C
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper
from ansibullbot.utils.git_tools import GitRepoWrapper


class GalaxyQueryTool:

    GALAXY_FQCNS = None
    GALAXY_FILES = None
    _collections = None
    _baseurl = 'https://galaxy.ansible.com'
    _gitrepos = None
    _checkout_index_file = None
    _checkout_index = None

    def __init__(self, cachedir=None):
        if cachedir:
            self.cachedir = os.path.join(cachedir, 'galaxy')
        else:
            self.cachedir = '.cache/galaxy'
        if not os.path.exists(self.cachedir):
            os.makedirs(self.cachedir)
        self.tarcache = os.path.join(self.cachedir, 'galaxy_tars')
        if not os.path.exists(self.tarcache):
            os.makedirs(self.tarcache)
        #rq = os.path.join(self.cachedir, 'requests_cache')
        #requests_cache.install_cache(rq)
        self._checkout_index_file = os.path.join(self.cachedir, 'checkout_index.json')

        self._gitrepos = {}
        self._load_checkout_index()

        self.index_ecosystem()
        #self.index_galaxy()
        #self.index_collections()

    def _get_cached_url(self, url, days=0):
        cachedir = os.path.join(self.cachedir, 'urls')
        if not os.path.exists(cachedir):
            os.makedirs(cachedir)
        cachefile = os.path.join(cachedir, url.replace('/', '__'))
        if os.path.exists(cachefile):
            with open(cachefile, 'r') as f:
                fdata = json.loads(f.read())
            jdata = fdata['result']
            ts = fdata['timestamp']
            now = datetime.datetime.now()
            ts = datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S.%f')
            if (now - ts).days <= days:
                return jdata

        rr = requests.get(url)
        jdata = rr.json()

        with open(cachefile, 'w') as f:
            f.write(json.dumps({
                'timestamp': datetime.datetime.now().isoformat(),
                'result': jdata
            }))

        return jdata

    def update(self):
        pass

    def index_ecosystem(self):
        # index the ansible-collections org
        token = C.DEFAULT_GITHUB_TOKEN
        gh = Github(login_or_token=token)
        gw = GithubWrapper(gh, cachedir=self.cachedir)
        ac = gw.get_org('ansible-collections')

        cloneurls = set()
        for repo in ac.get_repos():
            #print(repo)
            cloneurls.add(repo.clone_url)
        cloneurls = [x.replace('.git', '') for x in cloneurls]

        for curl in cloneurls:
            if curl.endswith('/overview'):
                continue
            if curl.endswith('/collection_template'):
                continue
            if curl.endswith('/.github'):
                continue
            if curl.endswith('/hub'):
                continue
            grepo = GitRepoWrapper(cachedir=self.cachedir, repo=curl, rebase=False)

            # is there a galaxy.yml at the root level?
            if grepo.exists('galaxy.yml'):
                meta = yaml.load(grepo.get_file_content('galaxy.yml'))
                fqcn = '%s.%s' % (meta['namespace'], meta['name'])
                self._gitrepos[fqcn] = grepo
            else:
                # multi-collection repos ... sigh.
                galaxyfns = grepo.find('galaxy.yml')

                if galaxyfns:
                    for gfn in galaxyfns:
                        meta = yaml.load(grepo.get_file_content(gfn))
                        fqcn = '%s.%s' % (meta['namespace'], meta['name'])
                        _grepo = GitRepoWrapper(cachedir=self.cachedir, repo=curl, rebase=False, context=os.path.dirname(gfn))
                        self._gitrepos[fqcn] = _grepo
                else:

                    fqcn = None
                    bn = os.path.basename(curl)

                    # enumerate the url?
                    if '.' in bn:
                        fqcn = bn

                    # try the README?
                    if fqcn is None:
                        for fn in ['README.rst', 'README.md']:
                            if fqcn:
                                break
                            if not grepo.exists(fn):
                                continue
                            fdata = grepo.get_file_content(fn)
                            if not '.' in fdata:
                                continue
                            lines = fdata.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line.lower().startswith('ansible collection:'):
                                    fqcn = line.split(':')[-1].strip()
                                    break

                    # lame ...
                    if fqcn is None:
                        fqcn = bn + '._community'

                    self._gitrepos[fqcn] = grepo

        # scrape the galaxy collections api
        nexturl = self._baseurl + '/api/v2/collections/'
        while nexturl:
            #rr = requests.get(nexturl)
            #jdata = rr.json()
            jdata = self._get_cached_url(nexturl)
            nexturl = jdata.get('next_link')
            if nexturl:
                nexturl = self._baseurl + nexturl

            for res in jdata.get('results', []):
                fqcn = '%s.%s' % (res['namespace']['name'], res['name'])
                if fqcn in self._gitrepos:
                    continue
                lv = res['latest_version']['href']
                #print(lv)
                #lvrr = requests.get(lv)
                #lvdata = lvrr.json()
                lvdata = self._get_cached_url(lv)
                rurl = lvdata.get('metadata', {}).get('repository')
                if rurl is None:
                    rurl = lvdata['download_url']
                grepo = GitRepoWrapper(cachedir=self.cachedir, repo=rurl, rebase=False)
                self._gitrepos[fqcn] = grepo

        # reconcile all things ...
        self.GALAXY_FQCNS = sorted(set(self._gitrepos.keys()))
        self.GALAXY_FILES = {}
        for fqcn,gr in self._gitrepos.items():
            if fqcn.startswith('testing.'):
                continue
            for fn in gr.files:
                if fn not in self.GALAXY_FILES:
                    self.GALAXY_FILES[fn] = set()
                self.GALAXY_FILES[fn].add(fqcn)
    
    def index_galaxy(self):
        self.GALAXY_FQCNS = set()

        url = 'https://sivel.eng.ansible.com/api/v1/collections/file_map'
        rr = requests.get(url)
        self.GALAXY_FILES = rr.json()

        for k,v in self.GALAXY_FILES.items():
            for fqcn in v:
                self.GALAXY_FQCNS.add(fqcn)

        url = 'https://sivel.eng.ansible.com/api/v1/collections/list'
        rr = requests.get(url)
        self.GALAXY_MANIFESTS = rr.json()

        self._verify_galaxy_files()

    def _verify_galaxy_files(self):
        for k,v in self.GALAXY_FILES.items():
            for fqcn in v:
                if not self.collection_file_exists(fqcn, k):
                    if fqcn in self.GALAXY_FILES[k]:
                        self.GALAXY_FILES[k].remove(fqcn)

    def _load_checkout_index(self):
        ci = {}
        if os.path.exists(self._checkout_index_file):
            with open(self._checkout_index_file, 'r') as f:
                ci = json.loads(f.read())
        for k,v in ci.items():
            ci[k]['updated'] = datetime.datetime.strptime(v['updated'], '%Y-%m-%dT%H:%M:%S.%f')
        self._checkout_index = copy.deepcopy(ci)

    def _save_checkout_index(self):
        ci = copy.deepcopy(self._checkout_index)
        for k,v in ci.items():
            ci[k]['updated'] = v['updated'].isoformat()
        with open(self._checkout_index_file, 'w') as f:
            f.write(json.dumps(ci))

    def get_repo_for_collection(self, fqcn):
        today = datetime.datetime.now()

        if fqcn not in self._gitrepos:

            # reduce the number of requests ...
            try:
                rurl = self._checkout_index.get(fqcn, {}).get('url')
            except AttributeError as e:
                print(e)
                import epdb; epdb.st()

            if rurl is None:
                # https://galaxy.ansible.com/api/v2/collections/devoperate/base/
                curl = self._baseurl + '/api/v2/collections/' + fqcn.replace('.', '/') + '/'
                rr = requests.get(curl)
                jdata = rr.json()
                vurl = jdata['latest_version']['href']
                rr2 = requests.get(vurl)
                jdata2 = rr2.json()
                rurl = jdata2.get('metadata', {}).get('repository')

            # reduce the number of clones and rebases ...
            needs_rebase = False
            if fqcn not in self._checkout_index:
                needs_rebase = True
            elif not self._checkout_index.get(fqcn, {}).get('checkout'):
                needs_rebase = True
            elif not self._checkout_index.get(fqcn, {}).get('updated'):
                needs_rebase = True
            elif (today - self._checkout_index[fqcn]['updated']).days > 0:
                needs_rebase = True

            logging.info('checkout %s -> %s' % (fqcn, rurl))
            grepo = GitRepoWrapper(cachedir=self.cachedir, repo=rurl, rebase=needs_rebase)
            self._gitrepos[fqcn] = grepo

            # keep the last updated time if not rebased ...
            if needs_rebase:
                updated = datetime.datetime.now()
            else:
                updated = self._checkout_index[fqcn]['updated']

            self._checkout_index[fqcn] = {
                'url': rurl,
                'fqcn': fqcn,
                'checkout': grepo.checkoutdir,
                'updated': updated
            }
            self._save_checkout_index()

        return self._gitrepos[fqcn]

    def collection_file_exists(self, fqcn, filename):
        repo = self.get_repo_for_collection(fqcn)
        exists = repo.exists(filename, loose=True)
        return exists

    def index_collections(self):

        self._collections = {}

        # make the list of known collections
        jdata = {'next': '/api/v2/collections/?page=1'}
        while jdata.get('next'):
            rr = requests.get(self._baseurl + jdata['next'])
            jdata = rr.json()
            for collection in jdata['results']:
                key = '%s.%s' % (collection['namespace']['name'], collection['name'])
                self._collections[key] = copy.deepcopy(collection)

        # get the known versions
        for cn,cd in self._collections.items():
            versions = {}
            jdata = {'next': cd['versions_url']}
            while jdata.get('next'):
                logging.debug(jdata['next'])
                rr = requests.get(jdata['next'])
                jdata = rr.json()
                for version in jdata['results']:
                    versions[version['version']] = version['href']
            self._collections[cn]['versions'] = copy.deepcopy(versions)

        # fetch every version and make file lists
        for cn,cd in self._collections.items():
            for version,vurl in cd['versions'].items():
                # download it
                durl = self._baseurl + '/download/' + cn.replace('.', '-') + '-' + version + '.tar.gz'
                tarfn = os.path.join(self.tarcache, os.path.basename(durl))
                if not os.path.exists(tarfn):
                    logging.debug('%s -> %s' % (durl, tarfn))
                    rr = requests.get(durl, stream=True)
                    with open(tarfn, 'wb') as f:
                        f.write(rr.raw.read())
                # list it
                tarfn_json = tarfn + '.json'
                if os.path.exists(tarfn_json):
                    with open(tarfn_json, 'r') as f:
                        filenames = json.loads(f.read())
                else:
                    logging.debug(tarfn)
                    with tarfile.open(tarfn, 'r:gz') as f:
                        filenames = f.getnames()
                    with open(tarfn_json, 'w') as f:
                        f.write(json.dumps(filenames))
                self._collections[cn]['versions'][version] = {
                    'url': vurl,
                    'files': filenames[:]
                }

    @property
    def namespaces(self):
        return sorted(list(self._collections.keys()))

    def find(self, filename):
        '''find what collection a file path or segment went to'''
        results = []

        fparts = filename.split('/')
        for cn,cd in self._collections.items():
            for version,vd in cd['versions'].items():
                if filename in vd['files']:
                    results.append({'collection': cn,'version': version, 'match': filename, 'score': 100})
                    continue
                for fn in vd['files']:
                    if filename in fn:
                        if os.path.basename(fn) == filename:
                            score = 100
                        elif fn.endswith(filename):
                            if os.path.basename(filename) == os.path.basename(fn):
                                score = 99
                            else:
                                score = 70
                        else:
                            bparts = fn.split('/')
                            score = sum([10 for x in bparts if x in fparts])
                        results.append({'collection': cn,'version': version, 'match': fn, 'score': score})
        results = sorted(results, key=lambda x: x['score'])

        return results

    def search_galaxy(self, component):
        '''Is this a file belonging to a collection?'''

        matches = []

        if os.path.basename(component) == '__init__.py':
            return matches

        candidates = []
        patterns = [component]

        dirmap = {
            'contrib/inventory': 'scripts/inventory',
            'lib/ansible/modules': 'plugins/modules',
            'lib/ansible/module_utils': 'plugins/module_utils',
            'lib/ansible/plugins': 'plugins',
            'test/integration': 'tests/integration',
            'test/units/modules': 'tests/units/modules',
            'test/units/module_utils': 'tests/units/module_utils',
        }

        for k,v in dirmap.items():
            if component.startswith(k):
                # look for the full path including subdirs ...
                _component = component.replace(k + '/', v + '/')
                if _component not in dirmap and _component not in dirmap.values():
                    patterns.append(_component)

                # add the short path in case the collection does not have subdirs ...
                segments = _component.split('/')
                if len(segments) > 3:
                    thispath = os.path.join(v, os.path.basename(_component))
                    if thispath not in dirmap and thispath not in dirmap.values():
                        patterns.append(os.path.join(v, os.path.basename(_component)))

                # find parent folder for new modules ...
                if v != 'plugins':
                    if os.path.dirname(_component) not in dirmap and os.path.dirname(_component) not in dirmap.values():
                        patterns.append(os.path.dirname(_component))

                break

        # hack in patterns for deprecated files
        for x in patterns[:]:
            if x.endswith('.py'):
                bn = os.path.basename(x)
                bd = os.path.dirname(x)
                if bn.startswith('_'):
                    bn = bn.replace('_', '', 1)
                    patterns.append(os.path.join(bd, bn))

        '''
        patterns = sorted([x for x in patterns if not x.startswith('lib/')])
        filenames = [x for x in patterns if x.endswith('.py')]
        dirnames = [x for x in patterns if not x.endswith('.py')]
        patterns = filenames + dirnames
        import epdb; epdb.st()
        '''

        #if component.startswith('lib/ansible/plugins'):
        #    import epdb; epdb.st()

        #if component.startswith('lib/ansible/modules'):
        #    import epdb; epdb.st()

        #if component.startswith('test/n') or component.startswith('tests/'):
        #    import epdb; epdb.st()

        for pattern in patterns:

            if candidates:
                break

            for key in self.GALAXY_FILES.keys():
                if not (pattern in key or key == pattern):
                    continue

                logging.info(u'matched %s to %s:%s' % (component, key, self.GALAXY_FILES[key]))
                candidates.append(key)
                break

        if candidates:
            for cn in candidates:
                for fqcn in self.GALAXY_FILES[cn]:
                    #if fqcn.startswith('testing.'):
                    #    continue
                    matches.append('collection:%s:%s' % (fqcn, cn))
            matches = sorted(set(matches))

        return matches

    def fuzzy_search_galaxy(self, component):

        matched_filenames = []

        if component.endswith('__init__.py'):
            return matched_filenames

        if component.startswith('lib/ansible/modules'):
            bn = os.path.basename(component)
            bn = bn.replace('.py', '')
            if '_' in bn:
                bparts = bn.split('_')
                for x in reversed(range(0, len(bparts))):
                    prefix = '_'.join(bparts[:x])
                    if not prefix:
                        continue
                    for key in self.GALAXY_FILES.keys():
                        keybn = os.path.basename(key)
                        if keybn.startswith(prefix):
                            logging.info('galaxy fuzzy match %s == %s' % (keybn, prefix))
                            logging.info('galaxy fuzzy match %s == %s' % (key, component))
                            #import epdb; epdb.st()

                            for fqcn in self.GALAXY_FILES[key]:
                                matched_filenames.append('collection:%s:%s' % (fqcn, component))
                                #matched_filenames.append('collection:%s:%s' % (fqcn, key))

                            break
                    if matched_filenames:
                        break

        import epdb; epdb.st()
        return matched_filenames
