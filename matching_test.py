#!/usr/bin/env python


import json
import glob
import logging
import os

import ansibullbot.constants as C

from ansibullbot.utils.file_tools import FileIndexer
from ansibullbot.utils.gh_gql_client import GithubGraphQLClient
from ansibullbot.utils.moduletools import ModuleIndexer
from ansibullbot.utils.webscraper import GithubWebScraper
from ansibullbot.triagers.plugins.component_matching import get_component_match_facts

from pprint import pprint


LABELS = []
CACHEDIR = os.path.expanduser('~/.ansibullbot/cache')
METADIR = '/home/jtanner/workspace/scratch/metafiles'
METAFILES = glob.glob('{}/*.json'.format(METADIR))


#EXCLUSIONS = [
#    'https://github.com/ansible/ansible/issues/26763',
#    'https://github.com/ansible/ansible/issues/26883'
#]

EXPECTED = {
    'https://github.com/ansible/ansible/issues/25863': 'lib/ansible/modules/identity/ipa/ipa_sudorule.py',
    'https://github.com/ansible/ansible/issues/26763': 'lib/ansible/modules/cloud/openstack/os_user_role.py',
    'https://github.com/ansible/ansible/issues/26883': 'lib/ansible/modules/network/netconf/netconf_config.py',
}



class IssueWrapperMock(object):
    def __init__(self, meta):
        self.meta = meta

    def is_issue(self):
        return self.meta.get('is_issue', False)

    def is_pullrequest(self):
        return self.meta.get('is_pullrequest', False)

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

    FI = FileIndexer(checkoutdir=CACHEDIR)
    GQLC = GithubGraphQLClient(C.DEFAULT_GITHUB_TOKEN)
    GWS = GithubWebScraper(cachedir=CACHEDIR)
    MI = ModuleIndexer(cachedir=CACHEDIR, gh_client=GQLC, blames=False, commits=False)

    for MF in METAFILES:
        with open(MF, 'rb') as f:
            meta = json.loads(f.read())

        if not meta.get('is_issue'):
            continue

        component = meta.get('template_data', {}).get('component_raw')
        if component:
            print('------------------------------------------')
            print(meta['html_url'])
            print(meta['title'])
            print(component)

            hurl = meta['html_url']
            iw = IssueWrapperMock(meta)
            cmf = get_component_match_facts(iw, meta, FI, MI, LABELS)

            # These are validated results and can be ignored
            if hurl in EXPECTED:
                if not EXPECTED[hurl] and not cmf.get('module_match'):
                    continue
                if EXPECTED[hurl] and cmf.get('module_match', {}).get('repo_filename') == EXPECTED[hurl]:
                    continue

            if not meta.get('module_match') and cmf.get('module_match'):
                print('ERROR: should not have module match')
                import epdb; epdb.st()

            if meta.get('module_match') and not cmf.get('module_match'):
                print('ERROR: no module match')
                import epdb; epdb.st()

            if meta.get('module_match'):

                mfile = meta['module_match']['repo_filename']
                mfile2 = cmf['module_match']['repo_filename']

                if mfile != mfile2:
                    print('ERROR: files do not match')
                    import epdb; epdb.st()

        #import epdb; epdb.st()


if __name__ == "__main__":
    main()
