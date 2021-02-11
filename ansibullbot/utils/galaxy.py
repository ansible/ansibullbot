import datetime
import json
import logging
import os

import requests
import yaml
from github import Github

import ansibullbot.constants as C
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.timetools import strip_time_safely
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper

GALAXY_BASE_URL = 'https://galaxy.ansible.com'

BLACKLIST_PATHS = [
    '.github',
    '.github/FUNDING.yml',
    '.github/lock.yml',
    'CHANGELOG.md',
    'docs',
    'lib/ansible/module_utils/basic.py',
    'lib/ansible/module_utils/facts'
]

BLACKLIST_FQCNS = [
    #'frankshen01.testfortios', # not till they are allocated to fortinet.fortios
    'alancoding.awx',
    'alancoding.cloud',
    'alancoding.vmware',
    'alikins.collection_inspect',
    'arillso.test_do_not_use',
    'felixfontein.tools',
    'fragmentedpacket.netbox_modules',
    'gavinfish.azuretest',
    'launchdarkly_labs.collection',
    'lukasjuhrich.ceph_ansible',
    'mattclay.aws',
    'mnecas.ovirt',
    'ovirt.ovirt_collection',
    'schmots1.ontap',
    'sh4d1.scaleway',
    'shanemcd.kubernetes',
    'sivel.jinja2',
    'sshnaidm.cloud',
    'sshnaidm.podman',
    'tawr1024.netbox_modules',
]

DIRMAP = {
    'contrib/inventory': 'scripts/inventory',
    'lib/ansible/plugins/action': 'plugins/action',
    'lib/ansible/plugins/callback': 'plugins/callback',
    'lib/ansible/plugins/connection': 'plugins/connection',
    'lib/ansible/plugins/filter': 'plugins/filter',
    'lib/ansible/plugins/inventory': 'plugins/inventory',
    'lib/ansible/plugins/lookup': 'plugins/lookup',
    'lib/ansible/modules': 'plugins/modules',
    'lib/ansible/module_utils': 'plugins/module_utils',
    'lib/ansible/plugins': 'plugins',
    'test/integration': 'tests/integration',
    'test/units/modules': 'tests/units/modules',
    'test/units/module_utils': 'tests/units/module_utils',
    'test': 'tests',
}


class GalaxyQueryTool:

    def __init__(self, cachedir=None):
        if cachedir:
            self.cachedir = os.path.join(cachedir, 'galaxy')
        else:
            self.cachedir = '.cache/galaxy'
        if not os.path.exists(self.cachedir):
            os.makedirs(self.cachedir)

        self._galaxy_files = {}
        self._gitrepos = {}

        self.index_ecosystem()

    def _get_cached_url(self, url, days=0):
        cachedir = os.path.join(self.cachedir, 'urls')
        if not os.path.exists(cachedir):
            os.makedirs(cachedir)
        cachefile = os.path.join(cachedir, url.replace('/', '__'))
        if os.path.exists(cachefile):
            with open(cachefile) as f:
                fdata = json.loads(f.read())
            jdata = fdata['result']
            ts = fdata['timestamp']
            now = datetime.datetime.now()
            ts = strip_time_safely(ts)
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
        nexturl = GALAXY_BASE_URL + '/api/v2/collections/?page_size=1000'
        while nexturl:
            jdata = self._get_cached_url(nexturl)
            nexturl = jdata.get('next_link')
            if nexturl:
                nexturl = GALAXY_BASE_URL + nexturl

            for res in jdata.get('results', []):
                fqcn = '%s.%s' % (res['namespace']['name'], res['name'])
                if res.get('deprecated'):
                    continue
                if fqcn in self._gitrepos:
                    continue
                lv = res['latest_version']['href']
                lvdata = self._get_cached_url(lv)
                rurl = lvdata.get('metadata', {}).get('repository')
                if rurl is None:
                    rurl = lvdata['download_url']
                grepo = GitRepoWrapper(cachedir=self.cachedir, repo=rurl, rebase=False)
                self._gitrepos[fqcn] = grepo

        self._galaxy_files = {}
        for fqcn,gr in self._gitrepos.items():
            if fqcn.startswith('testing.'):
                continue
            for fn in gr.files:
                if fn not in self._galaxy_files:
                    self._galaxy_files[fn] = set()
                self._galaxy_files[fn].add(fqcn)

    def search_galaxy(self, component):
        '''Is this a file belonging to a collection?'''
        matches = []

        if component.rstrip('/') in BLACKLIST_PATHS:
            return []

        if os.path.basename(component) == '__init__.py':
            return matches

        candidates = []
        patterns = [component]

        # we're not redirecting parent directories
        if component.rstrip('/') in DIRMAP:
            return []

        for k,v in DIRMAP.items():
            if component.startswith(k):
                # look for the full path including subdirs ...
                _component = component.replace(k + '/', v + '/')
                if _component not in DIRMAP and _component not in DIRMAP.values():
                    patterns.append(_component)

                # add the short path in case the collection does not have subdirs ...
                segments = _component.split('/')
                if len(segments) > 3:
                    basename = os.path.basename(_component)
                    if not basename == 'common.py':  # too many false positives
                        thispath = os.path.join(v, basename)
                        if thispath not in DIRMAP and thispath not in DIRMAP.values():
                            patterns.append(thispath)

                # find parent folder for new modules ...
                if v != 'plugins':
                    if os.path.dirname(_component) not in DIRMAP and os.path.dirname(_component) not in DIRMAP.values():
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

        for pattern in patterns:
            if candidates:
                break

            for key in self._galaxy_files.keys():
                if not (pattern in key or key == pattern):
                    continue
                if pattern == 'plugins/modules/':  # false positives
                    continue
                logging.info('matched %s to %s:%s' % (component, key, self._galaxy_files[key]))
                candidates.append(key)
                break

        if candidates:
            for cn in candidates:
                for fqcn in self._galaxy_files[cn]:
                    if fqcn in BLACKLIST_FQCNS:
                        continue
                    matches.append('collection:%s:%s' % (fqcn, cn))
            matches = sorted(set(matches))

        return matches

    def fuzzy_search_galaxy(self, component):
        matched_filenames = []

        if component.rstrip('/') in BLACKLIST_PATHS:
            return []

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
                    for key in self._galaxy_files.keys():
                        if key.startswith('roles/'):
                            continue
                        keybn = os.path.basename(key)
                        if keybn.startswith(prefix + '_'):
                            logging.info('galaxy fuzzy match %s startswith %s_' % (keybn, prefix))
                            logging.info('galaxy fuzzy match %s == %s' % (keybn, prefix))
                            logging.info('galaxy fuzzy match %s == %s' % (key, component))

                            for fqcn in self._galaxy_files[key]:
                                if fqcn in BLACKLIST_FQCNS:
                                    continue
                                matched_filenames.append('collection:%s:%s' % (fqcn, key))
                            break

        return matched_filenames
