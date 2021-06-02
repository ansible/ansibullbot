import datetime
import json
import logging
import os

import requests

from ansibullbot.utils.timetools import strip_time_safely


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
    'chrismeyersfsu.tower_modules',
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

        self._galaxy_files = self._get_cached_url('https://sivel.eng.ansible.com/api/v1/collections/file_map')
        self._collections_meta = self._get_cached_url('https://sivel.eng.ansible.com/api/v1/collections/list')

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

        for k, v in DIRMAP.items():
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
                    repo = self._collections_meta[fqcn]['manifest']['collection_info']['repository']
                    matches.append('collection:%s:%s:%s' % (fqcn, cn, repo))
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
                                repo = self._collections_meta[fqcn]['manifest']['collection_info']['repository']
                                matched_filenames.append('collection:%s:%s:%s' % (fqcn, key, repo))
                            break

        return matched_filenames
