#!/usr/bin/env python


import json
import glob
import logging
import os
import sys

import ansibullbot.constants as C

from ansibullbot.utils.file_tools import FileIndexer
from ansibullbot.utils.gh_gql_client import GithubGraphQLClient
from ansibullbot.utils.moduletools import ModuleIndexer
#from ansibullbot.utils.webscraper import GithubWebScraper
from ansibullbot.triagers.plugins.component_matching import get_component_match_facts

#from pprint import pprint


LABELS = []
CACHEDIR = os.path.expanduser('~/.ansibullbot/cache')
METADIR = '/home/jtanner/workspace/scratch/metafiles'
METAFILES = glob.glob('{}/*.json'.format(METADIR))
METAFILES = sorted(set(METAFILES))

# These do not match the cache but are the valid results
EXPECTED = {
    'https://github.com/ansible/ansible/issues/25863': [
        'lib/ansible/modules/identity/ipa/ipa_host.py',
        'lib/ansible/modules/identity/ipa/ipa_user.py',
        'lib/ansible/modules/identity/ipa/ipa_sudorule.py',
    ],
    'https://github.com/ansible/ansible/issues/26763': 'lib/ansible/modules/cloud/openstack/os_user_role.py',
    'https://github.com/ansible/ansible/issues/26883': 'lib/ansible/modules/network/netconf/netconf_config.py',
    'https://github.com/ansible/ansible/issues/23248': None,
    'https://github.com/ansible/ansible/issues/17843': 'lib/ansible/modules/net_tools/nmcli.py',
    'https://github.com/ansible/ansible/issues/29470': 'lib/ansible/modules/cloud/docker/docker_container.py',
    'https://github.com/ansible/ansible/issues/30362': 'lib/ansible/modules/cloud/amazon/ec2.py',
    'https://github.com/ansible/ansible/issues/28223': 'lib/ansible/modules/utilities/logic/import_playbook.py',
    'https://github.com/ansible/ansible/issues/26809': 'lib/ansible/modules/network/ios/ios_command.py',
    'https://github.com/ansible/ansible/issues/15491': 'lib/ansible/modules/source_control/git.py',
    'https://github.com/ansible/ansible/issues/27658': None,
    'https://github.com/ansible/ansible/issues/11775': None,
    'https://github.com/ansible/ansible/issues/12946': None,
    'https://github.com/ansible/ansible/issues/16993': None,
    'https://github.com/ansible/ansible/issues/17950': None, #BROKEN
    'https://github.com/ansible/ansible/issues/15695': 'lib/ansible/modules/system/setup.py',
    'https://github.com/ansible/ansible/issues/17029': 'lib/ansible/modules/system/setup.py',
    'https://github.com/ansible/ansible/issues/19067': 'lib/ansible/modules/system/setup.py',
    'https://github.com/ansible/ansible/issues/20752': 'lib/ansible/modules/system/setup.py',
    'https://github.com/ansible/ansible/issues/25897': 'lib/ansible/modules/system/setup.py',
    'https://github.com/ansible/ansible/issues/18513': None,
    'https://github.com/ansible/ansible/issues/20549': None, #BROKEN
    'https://github.com/ansible/ansible/issues/20768': None,
    'https://github.com/ansible/ansible/issues/20852': None,
    'https://github.com/ansible/ansible/issues/20965': None,
    'https://github.com/ansible/ansible/issues/20998': None,
    'https://github.com/ansible/ansible/issues/21299': None,
    'https://github.com/ansible/ansible/issues/22163': None,
    'https://github.com/ansible/ansible/issues/22248': 'lib/ansible/modules/files/file.py',
    'https://github.com/ansible/ansible/issues/22789': 'lib/ansible/modules/windows/win_package.ps1',
    'https://github.com/ansible/ansible/issues/23247': [
        'lib/ansible/modules/network/fortios/fortios_address.py',
        'lib/ansible/modules/network/fortios/fortios_config.py',
        'lib/ansible/modules/network/fortios/fortios_ipv4_policy.py'
    ],
    'https://github.com/ansible/ansible/issues/23836': 'lib/ansible/modules/files/copy.py',
    'https://github.com/ansible/ansible/issues/23909': 'lib/ansible/modules/cloud/openstack/os_keystone_endpoint.py',
    'https://github.com/ansible/ansible/issues/24302': 'lib/ansible/modules/files/stat.py',
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
    'https://github.com/ansible/ansible/issues/27903': [
        'lib/ansible/modules/network/cloudengine/ce_command.py',
        'lib/ansible/modules/network/cloudengine/ce_config.py'
    ],
}

SKIP = [
    'https://github.com/ansible/ansible/issues/13406',
    'https://github.com/ansible/ansible/issues/17950',
    'https://github.com/ansible/ansible/issues/22237', # Network modules
    'https://github.com/ansible/ansible/issues/22607', # contrib/inventory/linode
    'https://github.com/ansible/ansible/issues/24082', # synchronize + copy
    'https://github.com/ansible/ansible/issues/24971',
    'https://github.com/ansible/ansible/issues/25333',
    'https://github.com/ansible/ansible/issues/26485', # windows modules
    'https://github.com/ansible/ansible/issues/27136', # network modules
    'https://github.com/ansible/ansible/issues/27349', # selinux semodule
    'https://github.com/ansible/ansible/issues/28247', # Ansible core modules (system/systemd, system/service)
]



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

    ERRORS = []
    ERROR_COMPONENTS = []

    start_at = None
    if len(sys.argv) == 2:
        start_at = int(sys.argv[1])

    FI = FileIndexer(checkoutdir=CACHEDIR)
    GQLC = GithubGraphQLClient(C.DEFAULT_GITHUB_TOKEN)
    #GWS = GithubWebScraper(cachedir=CACHEDIR)
    MI = ModuleIndexer(cachedir=CACHEDIR, gh_client=GQLC, blames=False, commits=False)

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
            cmf = get_component_match_facts(iw, meta, FI, MI, LABELS)

            if component == 'core' and not cmf.get('module_match'):
                continue

            try:
                # These are validated results and can be ignored
                if hurl in EXPECTED:
                    if not EXPECTED[hurl] and not cmf.get('module_match'):
                        continue
                    if EXPECTED[hurl]:
                        mm = cmf.get('module_match', {})
                        if isinstance(mm, list) and isinstance(EXPECTED[hurl], list):
                            mfiles = sorted([x['repo_filename'] for x in mm])
                            if mfiles == sorted(EXPECTED[hurl]):
                                continue
                        else:
                            if mm and mm.get('repo_filename') == EXPECTED[hurl]:
                                continue

                # Trust the ondisk meta otherwise ...
                if not meta.get('module_match') and cmf.get('module_match'):
                    print('ERROR: should not have module match')
                    ERRORS.append(iw.html_url)
                    ERROR_COMPONENTS.append(component)
                    #import epdb; epdb.st()
                    pass

                if meta.get('module_match') and not cmf.get('module_match'):
                    print('ERROR: no module match')
                    ERRORS.append(iw.html_url)
                    ERROR_COMPONENTS.append(component)
                    #import epdb; epdb.st()
                    pass

                if meta.get('module_match'):

                    mfile = meta['module_match']['repo_filename']

                    if not isinstance(cmf['module_match'], list):
                        mfile2 = cmf['module_match']['repo_filename']
                    else:
                        #import epdb; epdb.st()
                        pass

                    if mfile != mfile2:

                        if os.path.basename(mfile).replace('_', '') != os.path.basename(mfile2).replace('_', ''):

                            print('ERROR: files do not match')
                            ERRORS.append(iw.html_url)
                            ERROR_COMPONENTS.append(component)
                            #import epdb; epdb.st()

            except Exception as e:
                logging.debug(e)
                continue

    import epdb; epdb.st()


if __name__ == "__main__":
    main()
