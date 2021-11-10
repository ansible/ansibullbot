#!/usr/bin/env python


import json
import glob
import logging
import os
import sys
import tempfile

import ansibullbot.constants as C

from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.component_tools import AnsibleComponentMatcher
from ansibullbot.utils.file_tools import FileIndexer
from ansibullbot.utils.gh_gql_client import GithubGraphQLClient
from ansibullbot.utils.moduletools import ModuleIndexer
from ansibullbot.plugins.component_matching import get_component_match_facts

from pprint import pprint


LABELS = []
CACHEDIR = os.path.expanduser('~/.ansibullbot/cache')
FIXTUREDIR = 'tests/fixtures/component_data'
MATCH_MAP = {}

METATAR = 'tests/fixtures/issuemeta/metafiles-2017-11-02.tar.gz'


class IssueWrapperMock:
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


def extract_metafiles():
    # make tempdir
    # extract files to tempdir
    # return list of json files in tempdir
    tarfile = os.path.abspath(METATAR)
    tdir = tempfile.mkdtemp()
    cmd = f'cd {tdir} ; tar xzvf {tarfile}'
    (rc, so, se) = run_command(cmd)
    metafiles = glob.glob(f'{tdir}/metafiles/*.json')
    metafiles= sorted(set(metafiles))
    return metafiles


def clean_metafiles(filenames):
    for x in filenames:
        os.remove(x)


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

    METAFILES = extract_metafiles()

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
    MI = ModuleIndexer(cachedir=CACHEDIR, gh_client=GQLC, blames=False, commits=False)

    CM = AnsibleComponentMatcher(cachedir=CACHEDIR)

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
            print(f'------------------------------------------ {total}|{IDMF}')
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
                    if f'docs.ansible.com/ansible/latest/{c_bn}_module.html' in component:
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
    fn = os.path.join(FIXTUREDIR, 'component_errors.json')
    with open(fn, 'wb') as f:
        f.write(json.dumps(ERRORS_COMPONENTS, indent=2, sort_keys=True))

    clean_metafiles(METAFILES)


if __name__ == "__main__":
    main()
