#!/usr/bin/env python3

import datetime
import json
import os

from pprint import pprint

from ansibullbot.triagers.plugins.collection_facts import get_collection_facts
from ansibullbot.utils.component_tools import AnsibleComponentMatcher
from ansibullbot.parsers.botmetadata import BotMetadataParser
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.wrappers.historywrapper import HistoryWrapper

from ansibullbot.utils.logs import set_logger
set_logger()


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
        if '+' in ts or len(hypens) > 2:
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
    pass

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

    '''
    @property
    def comments(self):
        import epdb; epdb.st()

    @property
    def labels(self):
        import epdb; epdb.st()
    '''


class MockIssueWrapper:
    def __init__(self, html_url, meta):
        self.html_url = html_url
        self.instance = MockIssueInstance(self.html_url, meta)
        self._meta = meta
        #self._hw = HistoryWrapper(self, usecache=True, cachedir='/home/jtanner/.ansibullbot/cache')
        self._hw = None
    
    def is_issue(self):
        return 'pull' not in self.html_url

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
    def template_data(self):
        return self._meta.get('template_data')

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


def parse_match_results():

    issues = {}

    with open('scratch/match_results.txt', 'r') as f:
        issue = None
        thiscomponent = ''
        thisjson = ''
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
                incomponet = False
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

    redirect = set()
    noredirect = set()
    nometa = set()

    cachedir = '/home/jtanner/.ansibullbot/cache'
    gitrepo = GitRepoWrapper(cachedir=cachedir, repo='https://github.com/ansible/ansible', commit=None)
    rdata = gitrepo.get_file_content(u'.github/BOTMETA.yml')
    botmeta = BotMetadataParser.parse_yaml(rdata)
    cm = AnsibleComponentMatcher(
        cachedir=cachedir,
        gitrepo=gitrepo,
        botmeta=botmeta,
        botmetafile=None,
        email_cache=None,
        usecache=True
    )

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

    print('# %s total issues|PRs without meta' % len(list(nometa)))
    print('# %s total issues|PRs not redirected to collections' % len(list(noredirect)))
    print('# %s total issues|PRs redirected to collections' % len(list(redirect)))

    import epdb; epdb.st()

if __name__ == "__main__":
    main()
