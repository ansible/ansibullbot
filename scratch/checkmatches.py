#!/usr/bin/env python3

import copy
import datetime
import glob
import json
import os

from ansibullbot.triagers.plugins.collection_facts import get_collection_facts
from ansibullbot.utils.component_tools import AnsibleComponentMatcher
from ansibullbot.parsers.botmetadata import BotMetadataParser
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.wrappers.historywrapper import HistoryWrapper
from ansibullbot.triagers.plugins.component_matching import get_component_match_facts
from ansibullbot.triagers.plugins.collection_facts import get_collection_facts

from ansibullbot.utils.logs import set_logger
set_logger()

from pprint import pprint


class MockActor:
    def __init__(self, event):
        self._event = event

    @property
    def id(self):
        import epdb; epdb.st()

    @property
    def login(self):
        return self._event.get('actor')

class MockEvent:
    def __init__(self, event):
        self._event = event

    @property
    def created_at(self):
        ts = self._event['created_at']
        hyphens = [x for x in ts if x == '-']
        if '+' in ts or len(hyphens) > 2:
            ts = datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S%z')
            #import epdb; epdb.st()
        else:
            ts = datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
        return ts

    @property
    def event(self):
        return self._event

    @property
    def id(self):
        return self._event.get('id')

    @property
    def actor(self):
        actor = MockActor(self._event)
        return actor

class MockComment(MockEvent):

    @property
    def user(self):
        return self.actor

    @property
    def body(self):
        return self._event.get('body', '')


class MockRepoWrapper:
    def __init__(self, repo_path):
        self.repo_path = repo_path


class MockIssueInstance:
    def __init__(self, html_url, meta):
        self.html_url = html_url
        self._meta = meta

    @property
    def number(self):
        return int(self.html_url.split('/')[-1])

    @property
    def updated_at(self):
        ts = self._meta['updated_at']
        ts = datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
        return ts


class MockIssueWrapper:
    def __init__(self, html_url, meta, gitrepo):
        self.html_url = html_url
        self.instance = MockIssueInstance(self.html_url, meta)
        self._meta = meta
        self._gitrepo = gitrepo
        self._hw = None
    
    def is_issue(self):
        return 'pull' not in self.html_url

    def is_pullrequest(self):
        return 'pull' in self.html_url

    @property
    def repo_path(self):
        return 'ansible/ansible'

    @property
    def repo(self):
        # issue.repo.repo_path
        return MockRepoWrapper(self.repo_path)

    @property
    def number(self):
        return int(self.html_url.split('/')[-1])

    @property
    def pullrequest(self):
        return None

    @property
    def files(self):
        if self.is_issue():
            return None
        return self._meta.get('filenames', [])

    @property
    def new_files(self):
        if self.is_issue():
            return None
        fns = self._meta.get('filenames', [])
        fns = [x for x in fns if x not in self._gitrepo.files]
        return fns

    @property
    def new_modules(self):
        if self.is_issue():
            return None
        fns = self.new_files
        fns = [x for x in fns if x.startswith('lib/ansible/modules')]
        return fns

    @property
    def renamed_files(self):
        return self._meta.get('renamed_filenames', [])

    @property
    def template_data(self):
        return self._meta.get('template_data')

    @property
    def title(self):
        return self._meta.get('title', '')

    @property
    def body(self):
        return self._meta.get('body', '')

    @property
    def component(self):
        return self.template_data.get('component name', '')

    @property
    def history(self):
        if self._hw is None:
            self._hw = HistoryWrapper(self, usecache=True, cachedir='/home/jtanner/.ansibullbot/cache')

        return self._hw

    @property
    def comments(self):
        comments = [x for x in self._meta['history'] if x['event'] == 'commented']
        comments = [MockComment(x) for x in comments]
        return comments

    @property
    def labels(self):
        labels = set()
        for x in self._meta['history']:
            if x['event'] == 'labeled':
                labels.add(x['label'])
            elif x['event'] == 'unlabled':
                labels.remove(x['label'])
        return list(labels)

    @property
    def events(self):
        events = [MockEvent(x) for x in self._meta['history']]
        return events

    @property
    def reactions(self):
        return []


def get_issues():
    prefix = '~/.ansibullbot/cache/ansible/ansible/issues'
    directories = glob.glob('%s/*' % os.path.expanduser(prefix))
    numbers = [os.path.basename(x) for x in directories]
    numbers = [int(x) for x in numbers if x.isdigit()]
    numbers = sorted(numbers)

    paths = []
    for number in numbers:
        fn = os.path.join(prefix, str(number), 'meta.json')
        fn = os.path.expanduser(fn)
        paths.append(fn)

    return paths


def parse_match_results():

    issues = {}

    with open('scratch/match_results.txt', 'r') as f:
        issue = None
        incomponent = False
        injson = False
        for line in f.readlines():

            if line.startswith('# http'):
                issue = line.replace('#', '').strip()
                issues[issue] = {
                    'component': None,
                    'matches': None
                }
                injson = False
                incomponent = False
                continue
            elif line.startswith('# component:'):
                incomponent = True
                issues[issue]['component'] = line.split(':', 1)[-1]
                continue
            elif line.startswith('############'):
                if incomponent:
                    incomponent = False
            elif line.startswith('{}'):
                issues[issue]['matches'] = '{}'
                injson = False
                continue
            elif line.startswith('{'):
                #issues[issue]['matches'] = line
                injson = True
            elif line.startswith('}'):
                if issues[issue]['matches'] is None:
                    #import epdb; epdb.st()
                    pass
                else:
                    issues[issue]['matches'] += line.strip()
                injson = False

            if incomponent:
                if issues[issue]['component'] is None:
                    issues[issue]['component'] = line
                else:
                    issues[issue]['component'] += line
                #thiscomponent += line

            if injson:
                if issues[issue]['matches'] is None:
                    issues[issue]['matches'] = line.strip()
                else:
                    issues[issue]['matches'] += line.strip()
                #thisjson += line
          
    for k,v in issues.items():
        if v['matches'] is not None:
            try:
                issues[k]['matches'] = json.loads(v['matches'])
            except json.decoder.JSONDecodeError as e:
                print(e)
                print(v['matches'])
                #import epdb; epdb.st()

    return issues


def main():

    tocheck = [
        #32226,
        #30361,
        #31006,
        #58674,
        #63611,
        #64320,
        #66891,
        #68784,
        69010,
    ]

    redirect = set()
    noredirect = set()
    nometa = set()

    cachedir = '/home/jtanner/.ansibullbot/cache'
    gitrepo = GitRepoWrapper(
        cachedir=cachedir,
        repo='https://github.com/ansible/ansible',
        commit=None,
        rebase=False
    )
    rdata = gitrepo.get_file_content(u'.github/BOTMETA.yml')
    botmeta = BotMetadataParser.parse_yaml(rdata)
    cm = AnsibleComponentMatcher(
        cachedir=cachedir,
        gitrepo=gitrepo,
        botmeta=botmeta,
        botmetafile=None,
        email_cache=None,
        usecache=True,
        use_galaxy=True
    )


    '''
    mr = parse_match_results()
    for issue in sorted(mr.keys(), key=lambda x: int(x.split('/')[-1]), reverse=True):

        print(issue)
        number = int(issue.split('/')[-1])
        #if number != 68709:
        #    continue
        print(number)
        mfile = os.path.join('~/.ansibullbot/cache/ansible/ansible/issues/%s' % number, 'meta.json')
        mfile = os.path.expanduser(mfile)
        if os.path.exists(mfile):
            with open(mfile, 'r') as f:
                imeta = json.loads(f.read())
        else:
            nometa.add(issue)
            imeta = {}

        if imeta:

            iw = MockIssueWrapper(issue, meta=imeta)
            cfacts = get_collection_facts(iw, cm, imeta)
            #pprint(cfacts)

            if cfacts.get('needs_collection_redirect') == True:
                redirect.add(issue)
            else:
                noredirect.add(issue)

            #if not imeta['is_backport']:
            #    import epdb; epdb.st()
    '''

    mmap = {}

    #gmatches = cm.search_ecosystem('contrib/inventory/ec2.py')
    #import epdb; epdb.st()

    mfiles = get_issues()
    for mfile in mfiles:
        with open(mfile, 'r') as f:
            imeta = json.loads(f.read())
        print(imeta['html_url'])
        number = int(imeta['html_url'].split('/')[-1])
        if number not in tocheck:
            continue

        newmeta = copy.deepcopy(imeta)
        iw = MockIssueWrapper(imeta['html_url'], meta=newmeta, gitrepo=gitrepo)
        #cmatches = cm.match_components(iw.title, iw.body, iw.component)
        cmmeta = get_component_match_facts(iw, cm, [])
        newmeta.update(cmmeta)
        cfmeta = get_collection_facts(iw, cm, newmeta)

        # check api deltas ...
        #cm1 = cm.match(iw)
        #cm2 = cm.match_components(iw.title, iw.body, iw.component, files=iw.files)
        #import epdb; epdb.st()

        print('component: %s' % iw.component)
        print(cmmeta['component_filenames'])
        #pprint(cfmeta)
        cf2vals = [x for x in list(cfmeta['collection_filemap'].values()) if x]
        cf1vals = [x for x in list(imeta['collection_filemap'].values()) if x]
        '''
        if cf1vals or cf2vals:
            pprint(cf1vals)
            pprint(cf2vals)
            #import epdb; epdb.st()
        '''
        '''
        if cf2vals != cf1vals:
            pprint(cf1vals)
            pprint(cf2vals)
            import epdb; epdb.st()
        '''
        pprint(cfmeta)
        import epdb; epdb.st()

    print('# %s total issues|PRs without meta' % len(list(nometa)))
    print('# %s total issues|PRs not redirected to collections' % len(list(noredirect)))
    print('# %s total issues|PRs redirected to collections' % len(list(redirect)))

    import epdb; epdb.st()

if __name__ == "__main__":
    main()
