#!/usr/bin/env python

import copy
import json
import logging
import os
import tarfile
import zipfile

import requests
import requests_cache


class GalaxyQueryTool:

    _collections = None
    _baseurl = 'https://galaxy.ansible.com'

    def __init__(self, cachedir=None):
        self.cachedir = cachedir or '.cache'
        if not os.path.exists(self.cachedir):
            os.makedirs(self.cachedir)
        self.tarcache = os.path.join(self.cachedir, 'galaxy_tars')
        if not os.path.exists(self.tarcache):
            os.makedirs(self.tarcache)
        rq = os.path.join(self.cachedir, 'requests_cache')
        requests_cache.install_cache(rq)
        self.index_collections()

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
