#!/usr/bin/env python


import json
import glob
import logging
import os
import sys

import ansibullbot.constants as C

from ansibullbot.utils.component_tools import ComponentMatcher
from ansibullbot.utils.file_tools import FileIndexer
from ansibullbot.utils.gh_gql_client import GithubGraphQLClient
from ansibullbot.utils.moduletools import ModuleIndexer
#from ansibullbot.utils.webscraper import GithubWebScraper
from ansibullbot.triagers.plugins.component_matching import get_component_match_facts

from pprint import pprint


LABELS = []
CACHEDIR = os.path.expanduser('~/.ansibullbot/cache')
FIXTUREDIR = 'tests/fixtures/component_data'
METADIR = '/home/jtanner/workspace/scratch/metafiles'
METAFILES = glob.glob('{}/*.json'.format(METADIR))
METAFILES = sorted(set(METAFILES))

'''
# These do not match the cache but are the valid results
EXPECTED = {
    'https://github.com/ansible/ansible/issues/25863': [
        'lib/ansible/modules/identity/ipa/ipa_host.py',
        'lib/ansible/modules/identity/ipa/ipa_user.py',
        'lib/ansible/modules/identity/ipa/ipa_sudorule.py',
    ],
    'https://github.com/ansible/ansible/issues/26763': 'lib/ansible/modules/cloud/openstack/os_user_role.py',
    'https://github.com/ansible/ansible/issues/24574': 'lib/ansible/modules/windows/setup.ps1',
    'https://github.com/ansible/ansible/issues/25333': 'lib/ansible/modules/files/tempfile.py',
    'https://github.com/ansible/ansible/issues/25384': None,
    'https://github.com/ansible/ansible/issues/25662': None,
    'https://github.com/ansible/ansible/issues/25946': 'lib/ansible/modules/network/nxos/nxos_hsrp.py',
    'https://github.com/ansible/ansible/issues/26003': 'lib/ansible/modules/cloud/azure/azure_rm_virtualmachine.py',
    'https://github.com/ansible/ansible/issues/26095': 'lib/ansible/modules/cloud/vmware/vmware_guest.py',
    'https://github.com/ansible/ansible/issues/26162': 'lib/ansible/modules/network/nxos/nxos_system.py',
    'https://github.com/ansible/ansible/issues/27024': 'lib/ansible/modules/utilities/logic/_include.py',
    'https://github.com/ansible/ansible/issues/27275': 'lib/ansible/modules/network/ios/ios_command.py',
    'https://github.com/ansible/ansible/issues/27836': 'lib/ansible/modules/net_tools/basics/get_url.py',
    #'https://github.com/ansible/ansible/issues/27903': [
    #    'lib/ansible/modules/network/cloudengine/ce_command.py',
    #    'lib/ansible/modules/network/cloudengine/ce_config.py'
    #],
    'https://github.com/ansible/ansible/issues/29470': 'lib/ansible/modules/cloud/docker/docker_container.py',
    'https://github.com/ansible/ansible/issues/27903': [
        'lib/ansible/modules/network/cloudengine/ce_command.py',
        'lib/ansible/modules/network/cloudengine/ce_config.py'
    ],
    'https://github.com/ansible/ansible/issues/27836': 'lib/ansible/modules/net_tools/basics/get_url.py',
    'https://github.com/ansible/ansible/issues/27024': 'lib/ansible/modules/utilities/logic/_include.py',
    'https://github.com/ansible/ansible/issues/26763': 'lib/ansible/modules/cloud/openstack/os_user_role.py',
    'https://github.com/ansible/ansible/issues/26162': 'lib/ansible/modules/network/nxos/nxos_system.py',
    'https://github.com/ansible/ansible/issues/26095': 'lib/ansible/modules/cloud/vmware/vmware_guest.py',
    'https://github.com/ansible/ansible/issues/26003': 'lib/ansible/modules/cloud/azure/azure_rm_virtualmachine.py',
    'https://github.com/ansible/ansible/issues/25946': 'lib/ansible/modules/network/nxos/nxos_hsrp.py',
    'https://github.com/ansible/ansible/issues/25897': 'lib/ansible/modules/system/setup.py',
    'https://github.com/ansible/ansible/issues/30852': 'lib/ansible/modules/cloud/docker/docker_container.py',
    'https://github.com/ansible/ansible/issues/30534': 'lib/ansible/inventory',
    'https://github.com/ansible/ansible/issues/30431': 'lib/ansible/modules/windows/win_regedit.ps1',
    'https://github.com/ansible/ansible/issues/30362': 'lib/ansible/modules/cloud/amazon/ec2.py',
    'https://github.com/ansible/ansible/issues/29796': 'lib/ansible/modules/cloud/amazon/iam.py',
    'https://github.com/ansible/ansible/issues/29423': [
        'lib/ansible/module_utils/ipa.py',
        'lib/ansible/utils/module_docs_fragments/ipa.py'
    ],
    'https://github.com/ansible/ansible/issues/29417': [
        'lib/ansible/module_utils/ipa.py',
        'lib/ansible/utils/module_docs_fragments/ipa.py'
    ],
    #'https://github.com/ansible/ansible/issues/25863': [
    #    'lib/ansible/module_utils/ipa.py',
    #    'lib/ansible/utils/module_docs_fragments/ipa.py'
    #],
    'https://github.com/ansible/ansible/issues/28223': 'lib/ansible/modules/utilities/logic/import_playbook.py',
    'https://github.com/ansible/ansible/issues/24572': 'lib/ansible/modules/windows/setup.ps1',
    'https://github.com/ansible/ansible/issues/24302': 'lib/ansible/modules/files/stat.py',
    'https://github.com/ansible/ansible/issues/22789': 'lib/ansible/modules/windows/win_package.ps1',
    'https://github.com/ansible/ansible/issues/15491': [
        'lib/ansible/modules/source_control/git.py',
        'test/integration/targets/git',
    ],
    'https://github.com/ansible/ansible/issues/26883': 'lib/ansible/modules/network/netconf',
    'https://github.com/ansible/ansible/issues/31502': [
        'lib/ansible/modules/windows/win_dsc.ps1'
        'lib/ansible/modules/windows/win_dsc.py',
    ],
    'https://github.com/ansible/ansible/issues/31107': 'lib/ansible/plugins/connection/netconf.py',
    'https://github.com/ansible/ansible/issues/31086': 'bin/ansible',
    'https://github.com/ansible/ansible/issues/31918': 'lib/ansible/modules/files/xml.py',
    'https://github.com/ansible/ansible/issues/31905': 'lib/ansible/modules/cloud/amazon/ec2_vpc_subnet.py',
    'https://github.com/ansible/ansible/issues/31901': 'lib/ansible/modules/network/nxos/nxos_config.py',
    'https://github.com/ansible/ansible/issues/31919': 'lib/ansible/modules/cloud/amazon/elb_target_group.py',
    'https://github.com/ansible/ansible/issues/31891': 'lib/ansible/modules/files/replace.py',
    'https://github.com/ansible/ansible/issues/31890': 'lib/ansible/modules/network/nxos/nxos_static_route.py',
    'https://github.com/ansible/ansible/issues/31888': 'lib/ansible/modules/network/nxos/nxos_ip_interface.py',
    'https://github.com/ansible/ansible/issues/31887': 'lib/ansible/modules/network/nxos/nxos_portchannel.py',
}
'''

'''
SKIP = [
    'https://github.com/ansible/ansible/issues/13406',
    'https://github.com/ansible/ansible/issues/17950',
    'https://github.com/ansible/ansible/issues/22237',  # Network modules
    'https://github.com/ansible/ansible/issues/22607',  # contrib/inventory/linode
    'https://github.com/ansible/ansible/issues/24082',  # synchronize + copy
    'https://github.com/ansible/ansible/issues/24971',
    'https://github.com/ansible/ansible/issues/25333',
    'https://github.com/ansible/ansible/issues/26485',  # windows modules
    'https://github.com/ansible/ansible/issues/27136',  # network modules
    'https://github.com/ansible/ansible/issues/27349',  # selinux semodule
    'https://github.com/ansible/ansible/issues/28247',  # Ansible core modules (system/systemd, system/service)
    'https://github.com/ansible/ansible/issues/13026',
    'https://github.com/ansible/ansible/issues/13278',
    'https://github.com/ansible/ansible/issues/15297'
    'https://github.com/ansible/ansible/issues/15902'
]
'''


MATCH_MAP = {}


class IssueWrapperMock(object):
    def __init__(self, meta):
        self.meta = meta

    def is_issue(self):
        return self.meta.get('is_issue', False)

    def is_pullrequest(self):
        return self.meta.get('is_pullrequest', False)

    @property
    def html_url(self):
        return self.meta.get('html_url')

    @property
    def title(self):
        return self.meta.get('title')

    @property
    def body(self):
        body = '\n'.join(['\n'.join(x) for x in self.meta['template_data'].items()])
        return body

    @property
    def template_data(self):
        return self.meta.get('template_data', {})


def load_expected():
    fn = os.path.join(FIXTUREDIR, 'component_expected_results.json')
    with open(fn, 'rb') as f:
        fdata = json.loads(f.read())
    return fdata


def save_expected(data):
    fn = os.path.join(FIXTUREDIR, 'component_expected_results.json')
    with open(fn, 'wb') as f:
        f.write(json.dumps(data, indent=2, sort_keys=True))


def load_match_map():
    fn = os.path.join(FIXTUREDIR, 'component_match_map.json')
    with open(fn, 'rb') as f:
        data = json.loads(f.read())
    return data

def save_match_map(data):
    fn = os.path.join(FIXTUREDIR, 'component_match_map.json')
    with open(fn, 'wb') as f:
        f.write(json.dumps(data, indent=2, sort_keys=True))

def load_skip():
    fn = os.path.join(FIXTUREDIR, 'component_skip.json')
    with open(fn, 'rb') as f:
        data = json.loads(f.read())
    return data


def save_skip(data):
    fn = os.path.join(FIXTUREDIR, 'component_skip.json')
    with open(fn, 'wb') as f:
        f.write(json.dumps(data, indent=2, sort_keys=True))


def set_logger():
    logging.level = logging.DEBUG

    logFormatter = \
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)


def main():

    set_logger()

    SKIP = load_skip()
    EXPECTED = load_expected()
    MATCH_MAP = load_match_map()


    ERRORS = []
    ERRORS_COMPONENTS = []

    start_at = None
    if len(sys.argv) == 2:
        start_at = int(sys.argv[1])

    FI = FileIndexer(checkoutdir=CACHEDIR)
    with open('/tmp/files.json', 'wb') as f:
        f.write(json.dumps(FI.files, indent=2))
    GQLC = GithubGraphQLClient(C.DEFAULT_GITHUB_TOKEN)
    #GWS = GithubWebScraper(cachedir=CACHEDIR)
    MI = ModuleIndexer(cachedir=CACHEDIR, gh_client=GQLC, blames=False, commits=False)

    #CM = ComponentMatcher(cachedir=CACHEDIR, module_indexer=MI, file_indexer=FI)
    CM = ComponentMatcher(cachedir=CACHEDIR)

    for k,v in MI.modules.items():
        if k in MATCH_MAP:
            MATCH_MAP.pop(k, None)
        kname = v.get('name')
        if kname not in MATCH_MAP:
            MATCH_MAP[kname] = v.get('repo_filename')
        if kname + ' module' not in MATCH_MAP:
            MATCH_MAP[kname + ' module'] = v.get('repo_filename')
        if kname + 'module: ' + kname not in MATCH_MAP:
            MATCH_MAP['module: ' + kname] = v.get('repo_filename')
        if kname + 'module ' + kname not in MATCH_MAP:
            MATCH_MAP['module ' + kname] = v.get('repo_filename')

        # /modules/remote_management/foreman/katello.py
        pname = k.replace('lib/ansible', '')
        if pname not in MATCH_MAP:
            MATCH_MAP[pname] = v.get('repo_filename')

        # ansible/modules/packaging/os/rpm_key.py
        pname = k.replace('lib/', '/')
        if pname not in MATCH_MAP:
            MATCH_MAP[pname] = v.get('repo_filename')

        # /ansible/modules/packaging/os/rpm_key.py
        pname = k.replace('lib/', '')
        if pname not in MATCH_MAP:
            MATCH_MAP[pname] = v.get('repo_filename')

        # ansible/lib/ansible/modules/monitoring/monit.py
        pname = 'ansible/' + k
        if pname not in MATCH_MAP:
            MATCH_MAP[pname] = v.get('repo_filename')

        # network/f5/bigip_gtm_wide_ip
        pname = k.replace('lib/ansible/modules/', '')
        pname = pname.replace('.py', '')
        pname = pname.replace('.ps1', '')
        if pname not in MATCH_MAP:
            MATCH_MAP[pname] = v.get('repo_filename')

        # network/f5/bigip_gtm_wide_ip.py
        pname = k.replace('lib/ansible/modules/', '')
        if pname not in MATCH_MAP:
            MATCH_MAP[pname] = v.get('repo_filename')

        # modules/packaging/os/pkgng.py
        pname = k.replace('lib/ansible/', '')
        if pname not in MATCH_MAP:
            MATCH_MAP[pname] = v.get('repo_filename')

    save_match_map(MATCH_MAP)

    total = len(METAFILES)
    for IDMF,MF in enumerate(METAFILES):

        if start_at and IDMF < start_at:
            continue

        with open(MF, 'rb') as f:
            meta = json.loads(f.read())

        if not meta.get('is_issue'):
            continue

        component = meta.get('template_data', {}).get('component_raw')

        #if component != 'Module `synchronize`':
        #if component != 'Module: include_role':
        #    continue

        if component:
            print('------------------------------------------ {}|{}'.format(total, IDMF))
            print(meta['html_url'])
            print(meta['title'])
            print(component)

            hurl = meta['html_url']
            if hurl in SKIP:
                continue

            # bad template or bad template parsing
            if len(component) > 100:
                continue

            iw = IssueWrapperMock(meta)
            if 'module' not in iw.body.lower() and 'module' not in iw.title.lower():
                continue

            expected_fns = []

            # OLD METHOD
            if hurl not in EXPECTED and component not in MATCH_MAP:
                cmf = get_component_match_facts(iw, meta, FI, MI, LABELS)
                expected_fns = cmf.get('module_match')
                if not isinstance(expected_fns, list):
                    expected_fns = [expected_fns]
                expected_fns = [x['repo_filename'] for x in expected_fns if x]
                if 'component_matches' in cmf:
                    expected_fns = [x['filename'] for x in cmf['component_matches']]
                expected_fns = sorted(set(expected_fns))

            # NEW METHOD
            cmr = CM.match_components(iw.title, iw.body, iw.template_data.get('component_raw'))
            cmr_fns = [x['repo_filename'] for x in cmr if x]
            cmr_fns = sorted(set(cmr_fns))

            # VALIDATE FROM EXPECTED IF KNOWN
            if hurl in EXPECTED:
                if EXPECTED[hurl] and not isinstance(EXPECTED[hurl], list):
                    expected_fns = [EXPECTED[hurl]]
                elif EXPECTED[hurl]:
                    expected_fns = EXPECTED[hurl]
                else:
                    expected_fns = []

            # USE THE CACHED MAP
            if component in MATCH_MAP:
                expected_fns = MATCH_MAP[component]
                if not isinstance(expected_fns, list):
                    expected_fns = [expected_fns]
            elif component.lower() in MATCH_MAP:
                expected_fns = MATCH_MAP[component.lower()]
                if not isinstance(expected_fns, list):
                    expected_fns = [expected_fns]
            elif component.startswith(':\n') and component.endswith(' module'):
                mapkey = component.lstrip(':\n')
                if mapkey in MATCH_MAP:
                    expected_fns = MATCH_MAP[mapkey]
                    if not isinstance(expected_fns, list):
                        expected_fns = [expected_fns]

            # OLD CODE USED ACTION PLUGINS INSTEAD OF MODULES
            if expected_fns != cmr_fns and hurl not in EXPECTED:
                if len(expected_fns) == 1 and len(cmr_fns) == 1 and 'plugins/action' in expected_fns[0]:
                    e_bn = os.path.basename(expected_fns[0])
                    c_bn = os.path.basename(cmr_fns[0])
                    if e_bn == c_bn:
                        MATCH_MAP[component] = cmr_fns
                        save_match_map(MATCH_MAP)
                        continue

            # DOCS URLS
            if expected_fns != cmr_fns and hurl not in EXPECTED:
                if len(cmr_fns) == 1 and 'lib/ansible/modules' in cmr_fns[0]:
                    c_bn = os.path.basename(cmr_fns[0])
                    if 'docs.ansible.com/ansible/latest/{}_module.html'.format(c_bn) in component:
                        MATCH_MAP[component] = cmr_fns
                        save_match_map(MATCH_MAP)
                        continue
                    elif CM.strategy in ['search_by_regex_urls']:
                        MATCH_MAP[component] = cmr_fns
                        save_match_map(MATCH_MAP)
                        continue

            # NXOS ISSUES HAVE NXOS_VERSION HEADER
            if '- nxos' in component:
                if len(cmr_fns) == 1:
                    if os.path.basename(cmr_fns[0]).replace('.py', '') in component:
                        MATCH_MAP[component] = cmr_fns
                        save_match_map(MATCH_MAP)
                        continue
                #import epdb; epdb.st()

            # ODDBALL MODULE COMPONENTS
            if len(cmr_fns) == 1 and 'lib/ansible/modules' in cmr_fns[0]:
                bn = os.path.basename(cmr_fns[0])
                bn = bn.replace('.py', '')
                bn = bn.replace('.ps1', '')
                if (bn in component or bn.lstrip('_') in component) and 'module' in component.lower():
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue
                elif component == '- ' + bn:
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue
                elif component == bn + '.py' or component == bn + '.ps1':
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue
                elif component == '_' + bn + '.py' or component == '_' + bn + '.ps1':
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue
                elif component == ':\n' + bn or component == ':\n' + bn.lstrip('_'):
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue

            # 'multiple modules', etc ...
            if component in CM.KEYWORDS or component.lower() in CM.KEYWORDS:
                if component in CM.KEYWORDS and CM.KEYWORDS[component] is None and not cmr_fns:
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue
                elif component.lower() in CM.KEYWORDS and CM.KEYWORDS[component.lower()] is None and not cmr_fns:
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue
                elif len(cmr_fns) == 1 and cmr_fns[0] == CM.KEYWORDS.get(component):
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue
                elif len(cmr_fns) == 1 and cmr_fns[0] == CM.KEYWORDS.get(component.lower()):
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue

            if component.lstrip('-').strip() in CM.KEYWORDS and len(cmr_fns) == 1:
                cname = component.lstrip('-').strip()
                if CM.KEYWORDS[cname] == cmr_fns[0]:
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue

            if component.endswith(' lookup') and len(cmr_fns) == 1 and 'lib/ansible/plugins/lookup' in cmr_fns[0]:
                MATCH_MAP[component] = cmr_fns
                save_match_map(MATCH_MAP)
                continue

            if component.endswith(' inventory script') and len(cmr_fns) == 1 and 'contrib/inventory' in cmr_fns[0]:
                MATCH_MAP[component] = cmr_fns
                save_match_map(MATCH_MAP)
                continue

            if component.startswith('ansible/lib') and len(cmr_fns) == 1:
                fn = cmr_fns[0]
                if 'ansible/' + fn == component:
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue

            if component.endswith(' inventory plugin') and len(cmr_fns) == 1:
                fn = cmr_fns[0]
                if fn.startswith('lib/ansible/plugins/inventory'):
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue

            if component == 'ec2.py' and cmr_fns and 'contrib/inventory/ec2.py' in cmr_fns:
                MATCH_MAP[component] = cmr_fns
                save_match_map(MATCH_MAP)
                continue

            if len(expected_fns) == 1 and len(cmr_fns) == 1:
                if os.path.basename(expected_fns[0]) == os.path.basename(cmr_fns[0]):
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)
                    continue

            # COMPARE AND RECORD
            if expected_fns != cmr_fns and hurl not in EXPECTED:

                if component in MATCH_MAP or component.lower() in MATCH_MAP:
                    if component.lower() in MATCH_MAP:
                        mmc = MATCH_MAP[component.lower()]
                    else:
                        mmc = MATCH_MAP[component]
                    if not isinstance(mmc, list):
                        mmc == [mmc]
                    if mmc == cmr_fns:
                        EXPECTED[iw.html_url] = cmr_fns
                        save_expected(EXPECTED)
                        continue

                print('## COMPONENT ...')
                print(component)
                print('## EXPECTED ...')
                pprint(expected_fns)
                print('## RESULT ...')
                pprint(cmr_fns)
                print('## STRATEGIES ..')
                pprint(CM.strategy)
                pprint(CM.strategies)

                print('--------------------------------')
                res = raw_input('Is the result correct? (y/n/s/d): ')
                if res.lower() in ['y', 'yes']:
                    MATCH_MAP[component] = cmr_fns
                    EXPECTED[iw.html_url] = cmr_fns
                    save_expected(EXPECTED)
                    continue
                elif res.lower() in ['s', 'skip']:
                    SKIP.append(hurl)
                    save_skip(SKIP)
                    continue
                elif res.lower() in ['d', 'debug']:
                    import epdb; epdb.st()

                ERRORS.append(iw.html_url)
                ERRORS_COMPONENTS.append(
                    {
                        'url': iw.html_url,
                        'component': component,
                        'component_raw': iw.template_data.get('component_raw'),
                        'result': cmr_fns,
                        'expected': expected_fns,
                        'strategy': CM.strategy,
                        'strategies': CM.strategies
                    }
                )

            else:

                if component not in MATCH_MAP:
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)

                if hurl not in EXPECTED:
                    EXPECTED[hurl] = cmr_fns
                    save_expected(EXPECTED)

            continue

    pprint(ERRORS)
    with open('component_errors.json', 'wb') as f:
        f.write(json.dumps(ERRORS_COMPONENTS, indent=2, sort_keys=True))
    #import epdb; epdb.st()


if __name__ == "__main__":
    main()
