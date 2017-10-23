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
    with open('componet_expected_results.json', 'rb') as f:
        fdata = json.loads(f.read())
    return fdata


def save_expected(data):
    with open('componet_expected_results.json', 'wb') as f:
        f.write(json.dumps(data, indent=2, sort_keys=True))


def save_match_map(data):
    with open('componet_match_map.json', 'wb') as f:
        f.write(json.dumps(data, indent=2, sort_keys=True))


def load_skip():
    with open('componet_skip.json', 'rb') as f:
        data = json.loads(f.read())
    return data


def save_skip(data):
    with open('componet_skip.json', 'wb') as f:
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
    #save_skip(SKIP)
    SKIP = load_skip()

    EXPECTED = load_expected()

    ERRORS = []
    ERROR_COMPONENTS = []

    ERRORS2 = []
    ERROR2_COMPONENTS = []

    start_at = None
    if len(sys.argv) == 2:
        start_at = int(sys.argv[1])

    FI = FileIndexer(checkoutdir=CACHEDIR)
    GQLC = GithubGraphQLClient(C.DEFAULT_GITHUB_TOKEN)
    #GWS = GithubWebScraper(cachedir=CACHEDIR)
    MI = ModuleIndexer(cachedir=CACHEDIR, gh_client=GQLC, blames=False, commits=False)
    CM = ComponentMatcher(cachedir=CACHEDIR, module_indexer=MI, file_indexer=FI)

    total = len(METAFILES)
    for IDMF,MF in enumerate(METAFILES):

        if start_at and IDMF < start_at:
            continue

        with open(MF, 'rb') as f:
            meta = json.loads(f.read())

        if not meta.get('is_issue'):
            continue

        component = meta.get('template_data', {}).get('component_raw')
        if component:
            print('------------------------------------------ {}|{}'.format(total, IDMF))
            print(meta['html_url'])
            print(meta['title'])
            print(component)

            hurl = meta['html_url']
            if hurl in SKIP:
                continue

            iw = IssueWrapperMock(meta)
            if 'module' not in iw.body.lower() and 'module' not in iw.title.lower():
                continue

            # OLD METHOD
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

            # COMPARE AND RECORD
            if expected_fns != cmr_fns and hurl not in EXPECTED:

                print('## COMPONENT ...')
                print(component)
                print('## EXPECTED ...')
                pprint(expected_fns)
                print('## RESULT ...')
                pprint(cmr_fns)

                if component in MATCH_MAP:
                    if MATCH_MAP[component] == cmr_fns:
                        EXPECTED[iw.html_url] = cmr_fns
                        save_expected(EXPECTED)
                        continue

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

                ERRORS2.append(iw.html_url)
                ERROR2_COMPONENTS.append([iw.html_url, iw.template_data.get('component_raw'), cmr_fns, expected_fns, CM.strategy])


            else:

                if component not in MATCH_MAP:
                    MATCH_MAP[component] = cmr_fns
                    save_match_map(MATCH_MAP)

                if hurl not in EXPECTED:
                    EXPECTED[hurl] = cmr_fns
                    save_expected(EXPECTED)

            continue

    pprint(ERRORS2)
    import epdb; epdb.st()


if __name__ == "__main__":
    main()
