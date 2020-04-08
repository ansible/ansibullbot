#!/usr/bin/env python

import copy
import datetime
import json
import logging
import os
import tarfile
import zipfile

import requests
#import requests_cache

import ansibullbot.constants as C
from ansibullbot.utils.git_tools import GitRepoWrapper


class GalaxyQueryTool:

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
        rq = os.path.join(self.cachedir, 'requests_cache')
        #requests_cache.install_cache(rq)
        self._checkout_index_file = os.path.join(self.cachedir, 'checkout_index.json')

        self._gitrepos = {}

        self._load_checkout_index()

        #self.index_collections()

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
            rurl = self._checkout_index.get(fqcn, {}).get('url')
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
