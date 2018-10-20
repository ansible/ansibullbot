#!/usr/bin/env python


import argparse
import datetime
import glob
import hashlib
import json
import os
import pickle
import random
import requests
import six
import subprocess
import time

from pprint import pprint
from flask import Flask
from flask import jsonify
from flask import request

#from werkzeug.serving import WSGIRequestHandler
#WSGIRequestHandler.protocol_version = "HTTP/1.1"


app = Flask(__name__)


BASEURL = 'http://localhost:5000'
ERROR_TIMER = 0

TOKENS = {
    'AAA': 'ansibot'
}

ANSIBLE_PROJECT_ID = u'573f79d02a8192902e20e34b'
SHIPPABLE_URL = u'https://api.shippable.com'
ANSIBLE_PROVIDER_ID = u'562dbd9710c5980d003b0451'
ANSIBLE_RUNS_URL = u'%s/runs?projectIds=%s&isPullRequest=True' % (
    SHIPPABLE_URL,
    ANSIBLE_PROJECT_ID
)

# https://elasticread.eng.ansible.com/ansible-issues/_search
# https://elasticread.eng.ansible.com/ansible-pull-requests/_search
#	?q=lucene_syntax_here
#	_search accepts POST

########################################################
#   MOCK 
########################################################

def get_timestamp():
    # 2018-10-15T21:21:48.150184
    # 2018-10-10T18:25:49Z
    ts = datetime.datetime.now().isoformat()
    ts = ts.split('.')[0]
    ts += 'Z'
    return ts


def run_command(cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (so, se) = p.communicate()
    return (p.returncode, so, se)


class GithubMock(object):

    generate = False
    fixturedir = '/tmp/bot.fixtures'
    botcache = '/data/ansibot.production.cache'
    use_botcache = True
    ifile = '/tmp/fakeup/issues.p'
    efile = '/tmp/fakeup/events.p'
    ISSUES = {'github': {}}
    PULLS = {'github': {}}
    EVENTS = {}
    REACTIONS = {}
    COMMENTS = {}
    HISTORY = {}
    STATUS_HASHES = {}
    PR_STATUSES = {}
    PULL_COMMITS = {}
    COMMITS = {}
    GITCOMMITS = {}
    FILES = {}
    META = {}
    RUNS = {}

    def __init__(self):
        '''
        if self.use_botcache:
            self.load_ansibot_cache()
        else:
            self.seed_fake_issues()
        '''
        pass

    def fetch_fixtures(self, org, repo, number):
        key = (org, repo, int(number))

        fixdir = os.path.join(self.fixturedir, 'repos', org, repo, str(number))
        if not os.path.exists(fixdir):
            os.makedirs(fixdir)

        iurl = 'https://api.github.com/repos/%s/%s/issues/%s' % (org, repo, number)
        irr = requests.get(iurl)
        issue = irr.json()
        issue_headers = dict(irr.headers)
        self.write_fixture(fixdir, 'issue', issue, issue_headers)

        courl = issue['comments_url']
        corr = requests.get(courl)
        comments = corr.json()
        comments_headers = dict(corr.headers)
        self.write_fixture(fixdir, 'comments', comments, comments_headers)

        reurl = issue['url'] + '/reactions'
        rerr = requests.get(reurl, headers={'Accept': 'application/vnd.github.squirrel-girl-preview+json'})
        reactions = rerr.json()
        reactions_headers = dict(rerr.headers)
        self.write_fixture(fixdir, 'reactions', reactions, reactions_headers)

        eurl = issue['events_url']
        err = requests.get(eurl)
        events = err.json()
        events_headers = dict(err.headers)
        self.write_fixture(fixdir, 'events', events, events_headers)

        if issue.get('pull_request'):
            purl = issue['pull_request']['url']
            prr = requests.get(purl)
            pull = prr.json()
            pull_headers = dict(prr.headers)
            self.write_fixture(fixdir, 'pull_request', pull, pull_headers)

            curl = pull['commits_url']
            crr = requests.get(curl)
            commits = crr.json()
            commits_headers = dict(crr.headers)
            self.write_fixture(fixdir, 'commits', commits, commits_headers)

            for commit in commits:
                curl = commit['url']
                crr = requests.get(curl)
                commitx = crr.json()
                commitx_headers = dict(crr.headers)
                self.write_fixture(
                    fixdir,
                    'commit_%s' % commitx['sha'],
                    commitx,
                    commitx_headers
                )

                # git commits are somewhat different
                gcurl = commitx['commit']['url']
                gcrr = requests.get(gcurl)
                gcommitx = gcrr.json()
                gcommitx_headers = dict(gcrr.headers)
                self.write_fixture(
                    fixdir,
                    'gitcommit_%s' % commitx['sha'],
                    gcommitx,
                    gcommitx_headers
                )

            furl = purl + '/files'
            frr = requests.get(furl)
            files = frr.json()
            files_headers = dict(frr.headers)
            self.write_fixture(fixdir, 'files', files, files_headers)

            surl = pull['statuses_url']
            srr = requests.get(surl)
            statuses = srr.json()
            statuses_headers = dict(srr.headers)
            self.write_fixture(fixdir, 'pr_status', statuses, statuses_headers)

            # https://api.shippable.com/runs?projectIds=573f79d02a8192902e20e34b&runNumbers=75680
            # https://api.shippable.com/runs/58caf30337380a0800e31219
            runids = set()
            for status in statuses:
                # a finished job will have a target url ending with /summary
                #_trr = requests.get(status['target_url'])
                sparts = status['target_url'].split('/')
                if sparts[-1] == 'summary':
                    runid = sparts[-2]
                elif sparts[-1].isdigit():
                    runid = sparts[-1]
                else:
                    import epdb; epdb.st()
                runids.add(runid)

            for runid in runids:
                rurl = 'https://api.shippable.com/runs'
                rurl += '?'
                rurl += 'projectIds=%s' % ANSIBLE_PROJECT_ID
                rurl += '&'
                rurl += 'runNumbers=%s' % runid

                ridrr = requests.get(rurl)
                self.write_fixture(
                    fixdir,
                    'run_%s' % runid,
                    ridrr.json(),
                    dict(ridrr.headers)
                )
                #import epdb; epdb.st()

        #import epdb; epdb.st()

    def load_issue_fixtures(self, org, repo, number):
        number = int(number)
        key = (org, repo, number)
        bd = os.path.join(self.fixturedir, 'repos', org, repo, str(number))
        fns = sorted(glob.glob('%s/*' % bd))
        fns = [x for x in fns if not 'headers' in x]
        for fn in fns:
            bn = os.path.basename(fn)
            bn = os.path.splitext(bn)[0]

            with open(fn, 'r') as f:
                data = json.loads(f.read())
            data = self.replace_data_urls(data)

            if bn == 'issue':
                self.ISSUES['github'][key] = data
            elif bn == 'pull_request':
                self.PULLS['github'][key] = data
            elif bn == 'comments':
                self.COMMENTS[key] = data
            elif bn == 'reactions':
                self.REACTIONS[key] = data
            elif bn == 'events':
                self.EVENTS[key] = data
            elif bn == 'files':
                self.FILES[key] = data
            elif bn == 'commits':
                self.PULL_COMMITS[key] = data
            elif bn.startswith('commit_'):
                sha = bn.split('_')[-1]
                self.COMMITS[sha] = data
            elif bn.startswith('gitcommit_'):
                sha = bn.split('_')[-1]
                self.GITCOMMITS[sha] = data
            elif bn == 'pr_status':
                urls = [x['url'] for x in data]
                urls = sorted(set(urls))
                hexdigest = urls[0].split('/')[-1]
                self.STATUS_HASHES[key] = hexdigest
                self.PR_STATUSES[hexdigest] = data
            elif bn.startswith('run_'):
                runid = bn.replace('run_', '')                
                self.RUNS[runid] = data

    def replace_data_urls(self, data):
        '''Point ALL urls back to this instance instead of the origin'''
        data = json.dumps(data)
        data = data.replace('https://api.github.com', BASEURL)
        data = data.replace('https://github.com', BASEURL)
        data = data.replace('https://api.shippable.com', BASEURL)
        data = data.replace('https://app.shippable.com', BASEURL)
        data = json.loads(data)
        return data

    def write_fixture(self, directory, fixture_type, data, headers):
        with open(os.path.join(directory, '%s.json' % fixture_type), 'w') as f:
            f.write(json.dumps(data, indent=2, sort_keys=True))
        with open(os.path.join(directory, '%s.headers.json' % fixture_type), 'w') as f:
            f.write(json.dumps(headers, indent=2, sort_keys=True))

    def seed_fake_issues(self):
        for i in range(1, 1000):
            ispr = bool(random.getrandbits(1))
            if ispr or i == 1:
                GM.get_issue('ansible', 'ansible', i, itype='pull')
            else:
                GM.get_issue('ansible', 'ansible', i, itype='issue')

    def load_ansibot_cache(self):
        cmd = 'find %s -type f -name "meta.json"' % self.botcache
        (rc, so, se) = run_command(cmd)
        metafiles = [x.strip() for x in so.split('\n') if x.strip()]
        metafiles = [x for x in metafiles if '/ansible/ansible/' in x]
        metafiles = sorted(set(metafiles))

        i47087 = [x for x in metafiles if '47087' in x]

        metafiles = metafiles[::-1]
        metafiles = metafiles[:100]
        metafiles += i47087
        #metafiles = metafiles[:1000]
        #import epdb; epdb.st()

        total = len(metafiles)
        for idmf,mf in enumerate(metafiles):
            print('%s|%s %s' % (total, idmf, mf))

            bd = os.path.dirname(mf)
            parts = mf.split('/')
            if len(parts) != 10:
                continue

            org = parts[-5]
            repo = parts[-4]
            number = int(parts[-2])
            key = (org, repo, number)

            ifile = os.path.join(bd, 'issue.pickle')
            ffile = os.path.join(bd, 'files.pickle')
            rdfile = os.path.join(bd, 'raw_data.pickle')
            hfile = os.path.join(bd, 'history.pickle')
            cfile = os.path.join(bd, 'events.pickle')
            efile = os.path.join(bd, 'events.pickle')
            stfile = os.path.join(bd, 'pr_status.pickle')

            if not os.path.isfile(rdfile) and not os.path.isfile(ifile):
                continue

            if os.path.isfile(ifile):
                with open(ifile, 'r') as f:
                    issue = pickle.load(f)
                rawdata = issue._rawData
            else:
                with open(rdfile, 'r') as f:
                    rawdata = pickle.load(f)
                rawdata = rawdata[1]

            if rawdata['state'] != 'open':
                continue

            rawdata = json.dumps(rawdata)
            rawdata = rawdata.replace("https://api.github.com", BASEURL)
            rawdata = json.loads(rawdata)
            #rawdata['state'] = u'open'
            self.ISSUES['github'][key] = rawdata.copy()

            try:
                with open(mf, 'r') as f:
                    meta = json.loads(f.read())
                self.META[key] = meta.copy()
            except Exception as e:
                self.META[key] = {}

            if key not in self.EVENTS:
                self.EVENTS[key] = []

            with open(hfile, 'r') as f:
                history = pickle.load(f)
            self.HISTORY[key] = history['history']

            with open(cfile, 'r') as f:
                comments = pickle.load(f)
            comments = comments[1]
            for comment in comments:
                rd = comment._rawData
                rd = json.dumps(rd)
                rd = rd.replace("https://api.github.com", BASEURL)
                rd = rd.replace("https://github.com", BASEURL)
                rd = json.loads(rd)
                self.EVENTS[key].append(rd)

            with open(efile, 'r') as f:
                events = pickle.load(f)
            events = events[1]
            for event in events:
                rd = event._rawData
                rd = json.dumps(rd)
                rd = rd.replace("https://api.github.com", BASEURL)
                rd = rd.replace("https://github.com", BASEURL)
                rd = json.loads(rd)
                self.EVENTS[key].append(rd)

            if os.path.exists(stfile):
                with open(stfile, 'r') as f:
                    pr_status = pickle.load(f)
                pr_status = pr_status[-1]
                pr_status = json.dumps(pr_status)
                pr_status = pr_status.replace("https://api.github.com", BASEURL)
                pr_status = pr_status.replace("https://github.com", BASEURL)
                pr_status = json.loads(pr_status)
                ids = [x['url'].split('/')[-1] for x in pr_status]
                ids = sorted(set(ids))
                statusid = ids[0]
                self.STATUS_HASHES[key] = statusid
                self.PR_STATUSES[statusid] = pr_status[:]

            if os.path.exists(ffile):
                with open(ffile, 'r') as f:
                    ffdata = pickle.load(f)
                self.FILES[key] = []
                ffdata = ffdata[1]
                for ff in ffdata:
                    ffd = ff._rawData
                    ffd = json.dumps(ffd)
                    ffd = ffd.replace("https://api.github.com", BASEURL)
                    ffd = ffd.replace("https://github.com", BASEURL)
                    ffd = json.loads(ffd)
                    fid = ffd['contents_url'].split('=')[-1]
                    '''
                    if fid not in self.FILES:
                        self.FILES[fid] = {}
                    self.FILES[fid][ffd['filename']] = ffd
                    '''
                    self.FILES[key].append(ffd)
                    #import epdb; epdb.st()

            if 'pull' in rawdata['html_url']:
                # pullrequest_status in meta.json
                # pullrequest_reviews in meta.json
                # owner_pr in meta.json
                #import epdb; epdb.st()
                pass

            #if int(number) == 47087:
            #    import epdb; epdb.st()

        #import epdb; epdb.st()

    def get_issue_status_uuid(self, org, repo, number):
        # .../repos/ansible/ansibullbot/statuses/882849ea5f96f757eae148ebe59f504a40fca2ce
        key = (org, repo, int(number))
        #import epdb; epdb.st()
        if key not in self.STATUS_HASHES:
            hash_object = hashlib.sha256(str(key))
            self.STATUS_HASHES[key] = hash_object.hexdigest()
        return self.STATUS_HASHES[key]

    def get_status(self, hex_digest):
        '''
        key = None
        for k,v in self.STATUS_HASHES.items():
            if v == hex_digest:
                key = k 
                break
        status = self.PR_STATUSES.get(key, [])
        '''
        status = self.PR_STATUSES.get(hex_digest, [])
        # u'1d5b14446520e24186e4da40a4d5b68e0dfbcb43'
        #print('# return status: %s %s' % (hex_digest, status))
        #import epdb; epdb.st()
        if not status:
            import epdb; epdb.st()
        return status

    def get_issue(self, org, repo, number, itype='issue'):

        def get_labels(org, repo, number):
            labels = []
            events = self.EVENTS.get((org, repo, number), [])
            for event in events:
                if event['event'] == 'labeled':
                    labels.append(event['label'])
                elif event['event'] == ['unlabeled']:
                    labels = [x for x in labels if x['name'] != event['label']['name']]
            return labels

        key = (org, repo, int(number))
        if key in self.ISSUES['github']:
            return self.ISSUES['github'][key]

        if not self.generate:
            raise Exception('The Mocker was not run in generative mode')

        print('# creating %s %s' % (number, itype))

        url = BASEURL
        url += '/'
        url += 'repos'
        url += '/'
        url += org
        url += '/'
        url += repo
        url += '/'
        '''
        if itype.lower() in ['pull', 'pullrequest']:
            url += 'pulls'
        else:
            url += 'issues'
        '''
        url += 'issues'
        url += '/'
        url += str(number)

        h_url = BASEURL
        h_url += '/'
        h_url += org
        h_url += '/'
        h_url += repo
        h_url += '/'
        if itype.lower() in ['pull', 'pullrequest']:
            h_url += 'pull'
        else:
            h_url += 'issues'
        #h_url += 'issues'
        #h_url += 'issue'
        h_url += '/'
        h_url += str(number)

        e_url = BASEURL
        e_url += '/'
        e_url += org
        e_url += '/'
        e_url += repo
        e_url += '/'
        e_url += 'issues'
        e_url += '/'
        e_url += str(number)
        e_url += '/'
        e_url += 'events'

        payload = {
            'id': 1000 + int(number),
            'author_association': 'MEMBER',
            'assignees': [],
            'created_at': get_timestamp(), 
            'updated_at': get_timestamp(),
            'url': url,
            'events_url': e_url,
            'html_url': h_url,
            'number': int(number),
            'labels': get_labels(org, repo, int(number)),
            'user': {
                'login': 'foouser'
            },
            'title': 'this thing is broken',
            'body': '',
            'state': 'open'
        }

        if itype.lower() in ['pull', 'pullrequest']:
            pull_url = url.replace('issues', 'pulls')
            diff_url = pull_url + '.diff'
            patch_url = pull_url + '.patch'
            pull_h_url = h_url.replace('issues', 'pull')
            payload['pull_request'] = {
                "url": pull_url,
                "html_url": pull_h_url,
                "diff_url": diff_url,
                "patch_url": patch_url
            }

        self.ISSUES['github'][key] = payload.copy()
        self.save_data()

        #import epdb; epdb.st()
        pprint(payload)
        return payload

    def get_pullrequest(self, org, repo, number):

        key = (org, repo, int(number))
        if key in self.PULLS['github']:
            return self.PULLS['github'][key]

        if not self.generate:
            raise Exception('This mock is not in generative mode')

        issue = GM.get_issue(org, repo, number, itype='pull')

        '''
        issue = json.dumps(issue)
        issue = issue.replace('https://api.github.com', BASEURL)
        issue = issue.replace('https://github.com', BASEURL)
        issue = json.loads(issue)
        #import epdb; epdb.st()
        '''

        issue['url'] = issue['url'].replace('issues', 'pulls')
        issue['requested_reviewers'] = []
        issue['requested_teams'] = []
        issue['commits_url'] = issue['url'] + '/commits'
        issue['review_comments_url'] = issue['url'] + '/comments'
        issue['review_comment_url'] = issue['url'] + '/comments{/number}'
        issue['head'] = {
            'repo': {
                'name': repo,
                'full_name': issue['user']['login'] + '/' + repo,
                'url': BASEURL + '/repos/' + issue['user']['login'] + '/' + repo
            },
            'sha': '882849ea5f96f757eae148ebe59f504a40fca2ce'
        }
        issue['base'] = {
            'ref': 'devel'
        }
        issue['_links'] = {}
        issue['merged'] = False
        issue['mergeable'] = self.META[key].get('mergeable', True)
        issue['rebaseable'] = True
        issue['mergeable_state'] = self.META[key].get('mergeable_state', u'clean')
        issue['merged_by'] = None
        issue['review_comments'] = 0
        issue['commits'] = 1
        issue['additions'] = 10
        issue['deletions'] = 2
        issue['changed_files'] = 1

        #issue['author_association'] = 'CONTRIBUTOR'

        status_hash = self.get_issue_status_uuid(org, repo, number)
        issue['statuses_url'] = BASEURL + '/repos/' + org + '/' + repo + '/statuses/' + status_hash
        return issue

    def get_pullrequest_files(self, org, repo, number):
        return self.FILES.get((org, repo, int(number)), [])

    def get_commit(self, sha):
        return self.COMMITS.get(sha, None)

    def get_git_commit(self, sha):
        return self.GITCOMMITS.get(sha, None)

    def get_pullrequest_commits(self, org, repo, number):

        key = (org, repo, int(number))
        if key in self.PULL_COMMITS:
            return self.PULL_COMMITS[key]

        if not self.generate:
            raise Exception('The simulator is not in generative mode')

        issue = self.get_issue(org, repo, int(number))
        pull = self.get_pullrequest(org, repo, int(number))
        files = self.get_pullrequest(org, repo, int(number))
        history = self.HISTORY[(org, repo, int(number))]
        meta = self.META[(org, repo, int(number))]

        commits = []
        for x in range(0, pull['commits']):
            # https://api.github.com/repos/ansible/ansible/pulls/47087/commits
            # sha
            # nodeid
            # commit
            # url
            # html_url
            # comments_url
            # author
            # committer
            # parents
            import epdb; epdb.st()

        import epdb; epdb.st()


    def save_data(self):

        if self.use_botcache:
            return None

        with open(self.ifile, 'w') as f:
            #f.write(json.dumps(ISSUES))
            pickle.dump(self.ISSUES, f)

        with open(self.efile, 'w') as f:
            #f.write(json.dumps(EVENTS))
            pickle.dump(self.EVENTS, f)

    def load_data(self):

        if self.use_botcache:
            return None

        if os.path.exists(self.ifile):
            with open(self.ifile, 'r') as f:
                #ISSUES = json.loads(f.read()) 
                self.ISSUES = pickle.load(f)

        if os.path.exists(self.efile):
            with open(self.efile, 'r') as f:
                #EVENTS = json.loads(f.read()) 
                self.EVENTS = pickle.load(f)

    def get_issue_event(self, org, repo, eid):
        event = None
        for k,events in GM.EVENTS.items():
            for ev in events:
                if ev['id'] == eid:
                    event = ev.copy()
                    break
        return event

    def get_issue_events(self, org, repo, number):
        key = (org, repo, int(number))
        events = self.EVENTS.get(key, [])
        # do not return comments as events!
        events = [x for x in events if x['event'] != 'commented']
        return events

    def add_issue_event(self, org, repo, number, event):

        key = (org, repo, int(number))
        if key not in self.ISSUES:
            self.get_issue(org, repo, int(number))
        if key not in self.EVENTS:
            self.EVENTS[key] = []
        eid = 0
        for k,v in self.EVENTS.items():
            for ev in v:
                eid+=1
        eid += 1
        event['id'] = eid

        if event['event'] == 'commented':
            #https://api.github.com/repos/ansible/ansible/issues/comments/428709071
            event['url'] = '%s/repos/%s/%s/issues/comments/%s' % (BASEURL, org, repo, eid)
        else:
            event['url'] = '%s/repos/%s/%s/issues/events/%s' % (BASEURL, org, repo, eid)

        self.EVENTS[key].append(event)
        self.ISSUES['github'][key]['updated_at'] = event['updated_at']
        self.save_data()

    def add_issue_label(self, org, repo, number, label, username):
        event = {
            'event': 'labeled',
            'created_at': get_timestamp(),
            'updated_at': get_timestamp(),
            'label': {'name': label},
            'user': {
                'login': username
            },
            'actor': {
                'login': username
            }
        }
        self.add_issue_event(org, repo, number, event)

    def remove_issue_label(self, org, repo, number, label, username):
        event = {
            'event': 'unlabeled',
            'created_at': get_timestamp(),
            'updated_at': get_timestamp(),
            'label': {'name': label},
            'user': {
                'login': username
            },
            'actor': {
                'login': username
            }
        }
        self.add_issue_event(org, repo, number, event)

    def add_issue_comment(self, org, repo, number, body, username):
        event = {
            'event': 'commented',
            'created_at': get_timestamp(),
            'updated_at': get_timestamp(),
            'user': {
                'login': username
            },
            'actor': {
                'login': username
            },
            'body': request.json['body']
        }
        self.add_issue_event(org, repo, number, event)

    def get_issue_comments(self, org, repo, number):
        events = self.EVENTS.get((org, repo, number), [])
        comments = [x for x in events if x['event'] == 'commented']
        return comments


GM = GithubMock()


########################################################
#   ROUTES
########################################################

def error_time():
    global ERROR_TIMER
    print('ERROR_TIMER: %s' % ERROR_TIMER)
    ERROR_TIMER += 1
    if ERROR_TIMER >= 10000:
        ERROR_TIMER = 0
        return True
    else:
        return False


class InternalServerError(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        #return rv
        return None


@app.errorhandler(InternalServerError)
def throw_ise(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


'''
@app.before_first_request
def prep_server():
    if GM.ISSUES['github']:
        return None

    #import epdb; epdb.st()
    #GM.load_data()
    if not GM.ISSUES['github']:
        for i in range(1, 11):
            ispr = bool(random.getrandbits(1))
            if ispr or i == 1:
                GM.get_issue('ansible', 'ansible', i, itype='pull')
            else:
                GM.get_issue('ansible', 'ansible', i, itype='issue')

    #issue = GM.get_issue('ansible', 'ansible', 1)
    #import epdb; epdb.st()
'''


@app.route('/')
def root():
    return jsonify({})


@app.route('/rate_limit')
def rate_limit():
    reset = int(time.time()) + 10
    rl = {
        'resources': {
            'core': {
                'limit': 5000,
                'remaining': 5000,
                'reset': reset
            }
        },
        'rate': {
            'limit': 5000,
            'remaining': 5000,
            'reset': reset
        }
    }
    return jsonify(rl)


@app.route('/orgs/<path:path>')
def orgs(path):
    path_parts = path.split('/')
    print(six.text_type((len(path_parts),path_parts)))

    if error_time():
        raise InternalServerError(None, status_code=500)

    if len(path_parts) == 1:
        return jsonify({
            'assignees': [],
            'url': 'http://localhost:5000/orgs/' + path_parts[-1],
            'name': path_parts[-1],
            'id': 1,
            'created_at': '2018-01-08T20:25:21Z',
            'updated_at': '2018-01-08T20:25:21Z'
        })
    elif len(path_parts) == 2 and path_parts[-1] == 'members':
        return jsonify([])
    elif len(path_parts) == 2 and path_parts[-1] == 'teams':
        return jsonify([])


def dict_xpath_set(ddict, path, key, value):

    obj = ddict
    for ix in path:
        if ix not in obj:
            obj[ix] = {} 
        obj = obj[ix]

    if 'kwargs' not in obj:
        obj['kwargs'] = {}
    if 'nodes' not in obj:
        obj['nodes'] = []
    obj['kwargs'][key] = value

    #pprint(ddict)
    #import epdb; epdb.st()
    return ddict


def dict_xpath_add(ddict, path, value):
    obj = ddict
    for ix in path:
        if ix not in obj:
            obj[ix] = {} 
        obj = obj[ix]

    if 'kwargs' not in obj:
        obj['kwargs'] = {}
    if 'nodes' not in obj:
        obj['nodes'] = []
    obj['nodes'].append(value)
    return ddict


@app.route('/graphql', methods=['GET', 'POST'])
def graphql():
    # 127.0.0.1 - - [14/Oct/2018 23:03:10] "POST /graphql HTTP/1.1" 404 -

    headers = dict(request.headers)
    print(request.data)
    #payload = request.data
    print(request.json)
    payload = request.json
    print(payload)

    try:
        jdata = json.loads(request.data)
        print(jdata)
        print(jdata.keys())
        print(jdata['query'])
    except Exception as e:
        print('ERROR: %s' % e)


    qinfo = {}
    qpath = []
    qlines = jdata['query'].split('\n')
    for idl,ql in enumerate(qlines):
        # normalize
        ql = ql.replace('){', ') {')

        print('%s:: %s' % (idl,ql))

        # 1::     repository(owner:"ansible", name:"ansible") {
        if ql.rstrip().endswith('{'):
            if '(' in ql and ')' in ql:

                # repository
                qlkey = ql.lstrip().split('(')[0]
                if not qlkey:
                    continue
                qpath.append(qlkey)
                print('branch?: %s' % qlkey)

                #qinfo[qlkey] = {}
                ql = ql.strip()
                ql = ql.replace('repository(', '')
                ql = ql.replace('pullRequest(', '')
                ql = ql.replace(') {', '')

                # owner/name/etc
                parts = ql.split(',')            
                for part in parts:
                    key = part.split(':')[0].strip()
                    val = part.split(':')[-1].strip()
                    #qinfo[qlkey][key] = val

                    '''
                    print('# sending in ...')
                    print('\tpath: ' + str(qpath))
                    print('\tkey: ' + key)
                    print('\tval: ' + val)

                    print('# result ...')
                    '''
                    qinfo = dict_xpath_set(qinfo, qpath, key, val)
                    #pprint(qinfo)
                    #import epdb; epdb.st()
            elif ql.rstrip().endswith('{'):
                # new branch
                qlkey = ql.lstrip().split('{')[0]
                if not qlkey:
                    continue
                print('branch?: %s' % qlkey)
                qpath.append(qlkey)

        elif ql.rstrip().endswith('}'):
            qpath = qpath[:-1]

        elif '{' not in ql and '}' not in ql and ql.strip():
            # nodes
            node = ql.strip()
            print('node?: ' + ql)
            qinfo = dict_xpath_add(qinfo, qpath, node)


    print('# QINFO ...')
    pprint(qinfo)

    data = {}
    if 'repository' in qinfo:
        data['repository'] = {}
        if 'pullRequest' in qinfo['repository']:
            data['repository']['pullRequest'] = {}
            nodes = qinfo['repository']['pullRequest']['nodes'][:]
            if 'number' in qinfo['repository']['pullRequest']['kwargs']:
                issue = GM.get_issue(
                    'ansible',
                    'ansible',
                    qinfo['repository']['pullRequest']['kwargs']['number']
                )
                pprint(issue)
                for node in nodes:
                    node = node.replace('At', '_at')
                    data['repository']['pullRequest'][node] = issue[node.lower()]

        elif 'issues' in qinfo['repository'] or 'pullRequests' in qinfo['repository']:

            ikey = 'issues'
            if 'pullRequests' in qinfo['repository']:
                ikey = 'pullRequests'
            data['repository'][ikey] = {'edges': [] }

            issues_keys = []
            for k,v in GM.ISSUES['github'].items():
                #print(k)
                #pprint(v)
                if 'pullRequests' in qinfo['repository']:
                    if v.get('pull_request'):
                        issues_keys.append(k)
                elif not v.get('pull_request'):
                    issues_keys.append(k)

            print('# total keys: %s' % len(issues_keys))
            issues_keys = sorted(issues_keys)
            issues = []
            for ik in issues_keys:
                issue = GM.ISSUES['github'][ik]
                node = {}
                node['id'] = issue['id']
                node['url'] = issue['url']
                node['number'] = issue['number']
                node['state'] = issue['state']
                node['createdAt'] = issue['created_at']
                node['updatedAt'] = issue['updated_at']
                node['repository'] = {
                    'nameWithOwner': None
                }
                data['repository'][ikey]['edges'].append({'node': node.copy()})

        else:
            print('# UNHANDLED GRAPH ENDPOINT')

    print('# RESULT ...')
    pprint(data)
    return jsonify({'data': data})


@app.route('/repos/<path:path>', methods=['GET', 'POST', 'DELETE'])
def repos(path):
    # http://localhost/repos/ansible/ansible/labels
    # http://localhost/repos/ansible/ansible/issues/1/comments

    path_parts = path.split('/')
    print(six.text_type((len(path_parts),path_parts)))
    print(request.path)

    if error_time():
        raise InternalServerError(None, status_code=500)

    if len(path_parts) == 2:
        print('sending repo')
        payload = {
            'name': path_parts[-1],
            'url': BASEURL + '/repos/' + path_parts[-2] + '/' + path_parts[-1],
            'full_name': '/'.join([path_parts[-2],path_parts[-1]]),
            'created_at': '2012-03-06T14:58:02Z',
            'updated_at': get_timestamp()
        }
        pprint(payload)
        return jsonify(payload)

    auth = dict(request.headers)['Authorization']
    token = auth.split()[-1]
    username = TOKENS.get(token)
    org = path_parts[0]
    repo = path_parts[1]

    if len(path_parts) == 3 and path_parts[-1] == 'assignees':
        print('sending repo assignees')
        return jsonify([])

    if len(path_parts) == 3 and path_parts[-1] == 'labels':
        print('path: %s %s' % (path_parts, len(path_parts)))
        print('sending repo labels')
        return jsonify([])

    if len(path_parts) == 5 and path_parts[-1] == 'labels':
        # [u'ansible', u'ansible', u'issues', u'1', u'labels']
        if request.method in ['POST', 'PUT', 'DELETE']:
            number = int(path_parts[3])
            labels = request.json

            print('adding label(s) %s to %s by %s' % (labels, number, username))
            for label in labels:
                #if request.method == 'POST':
                #    GM.add_issue_label(org, repo, number, label, username)
                #elif request.method == 'DELETE':
                #    GM.remove_issue_label(org, repo, number, label, username)
                start = time.time()
                GM.add_issue_label(org, repo, number, label, username)
                stop = time.time()
                print('add label duration: %s' % (stop - start))

            return jsonify({})

    if len(path_parts) == 6 and path_parts[-2] == 'labels' and request.method == 'DELETE':
        # (6, [u'ansible', u'ansible', u'issues', u'47136', u'labels', u'community_review'] 
        number = int(path_parts[-3])
        label = path_parts[-1]
        GM.remove_issue_label(org, repo, number, label, username)
        #import epdb; epdb.st()
        return jsonify({})

    elif len(path_parts) == 5 and path_parts[-1] == 'comments':
        number = int(path_parts[3])

        if request.method == 'POST':
            print('adding comment(s) by %s' % username)
            GM.add_issue_comment(org, repo, number, request.json['body'], username)
            return jsonify({})
        else:
            comments = GM.get_issue_comments(org, repo, number)
            print('return %s comments for %s' % (len(comments), number))
            return jsonify(comments)

    elif len(path_parts) == 4 and path_parts[-2] == 'issues':
        print('sending issue')
        # [u'ansible', u'ansible', u'issues', u'1issues']
        if not path_parts[-1].isdigit():
            raise InternalServerError(None, status_code=500)
        #return jsonify(GM.get_issue(path_parts[0], path_parts[1], path_parts[-1]))
	issue = GM.get_issue(path_parts[0], path_parts[1], path_parts[-1])
        pprint(issue)
	resp = jsonify(issue)
	resp.headers['ETag'] = 'a00049ba79152d03380c34652f2cb612'
	return resp

    elif len(path_parts) == 5 and path_parts[-2] == 'comments':
        # (5, [u'ansible', u'ansible', u'issues', u'comments', u'2'])
        cid = int(path_parts[-1])
        comment = None
        for k,ev in GM.EVENTS:
            if ev['id'] == cid:
                comment = ev.copy()
                break
        print('sending comment: %s' % comment)
        return jsonify(comment)

    elif len(path_parts) == 5 and path_parts[-1] == 'events':
        number = int(path_parts[3])
        events = GM.get_issue_events(org, repo, number)
        print('sending %s events %s/%s/%s' % (len(events), org, repo, number))
        return jsonify(events)

    elif len(path_parts) == 5 and path_parts[-2] == 'events':
        # (5, [u'ansible', u'ansible', u'issues', u'events', u'3'])
        eid = int(path_parts[-1])
        event = GM.get_issue_event(org, repo, eid)
        print('# found event ...')
        pprint(event)
        return jsonify(event)

    elif len(path_parts) == 5 and path_parts[-1] == 'reactions':
        number = int(path_parts[3])
        key = (org, repo, int(number))
        events = GM.EVENTS.get(key, [])
        events = [x for x in events if x['event'] == 'reacted']
        print('sending %s reactions %s/%s/%s' % (len(events), org, repo, number))
        return jsonify(events)

    elif len(path_parts) == 2:
        return jsonify({})

    elif len(path_parts) == 4 and path_parts[-2] == 'pulls':
        # (4, [u'ansible', u'ansible', u'pulls', u'1'])
        issue = GM.get_pullrequest(path_parts[0], path_parts[1], path_parts[-1])
	resp = jsonify(issue)
	resp.headers['ETag'] = 'a00049ba79152d03380c34652f2cb612'
	return resp

    elif len(path_parts) == 4 and path_parts[-2] == 'statuses':
        status = GM.get_status(path_parts[-1])
        return jsonify(status)

    elif len(path_parts) == 5 and path_parts[-1] == 'commits':
        number = path_parts[-2]
        commits = GM.get_pullrequest_commits(org, repo, number)
        print('# return %s commits' % len(commits))
        return jsonify(commits)

    elif len(path_parts) in [4, 5] and path_parts[-2] == 'commits':
        # (4, [u'ansible', u'ansible', u'commits', u'1d5b14446520e24186e4da40a4d5b68e0dfbcb43'])
        # (5, [u'ansible', u'ansible', u'git', u'commits', u'1d5b14446520e24186e4da40a4d5b68e0dfbcb43'])
        hashid = path_parts[-1]
        if path_parts[2] == 'commits':
            commit = GM.get_commit(hashid)
        elif path_parts[2] == 'git':
            commit = GM.get_git_commit(hashid)
        print('# returning commit: %s' % commit)
        return jsonify(commit)

    elif len(path_parts) == 5 and path_parts[-1] == 'files':
        number = int(path_parts[-2])
        files = GM.get_pullrequest_files(org, repo, number)
        #import epdb; epdb.st()
        return jsonify(files)

    elif len(path_parts) == 5 and path_parts[-1] == 'reviews':
        return jsonify([])

    elif len(path_parts) == 4 and path_parts[2] == 'contents':
        return ''

    print('unhandled path for "repo" route ...')
    print(six.text_type((len(path_parts),path_parts)))


@app.route('/<path:path>', methods=['GET', 'POST'])
def abstract_path(path):
    # /ansible/ansible/issues/1

    print('# ABSTRACT PATH! - %s' % path)
    path_parts = path.split('/')
    print(six.text_type((len(path_parts),path_parts)))
    print(request.path)



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['fetch', 'load', 'generate'])
    parser.add_argument('--fixtures', default='/tmp/bot.fixtures')
    parser.add_argument('--count', type=int, default=None)
    parser.add_argument('--org', default='ansible')
    parser.add_argument('--repo', default='ansible')
    parser.add_argument('--number', type=int, default=None, action='append')
    args = parser.parse_args()

    GM.fixturedir = args.fixtures

    if args.action == 'fetch':
        # get the real upstream data for an issue and store it to disk
        for number in args.number:
            GM.fetch_fixtures(args.org, args.repo, number)
    else:
        if args.action == 'load':
            # use ondisk fixtures created by 'fetch'
            for number in args.number:
                GM.load_issue_fixtures(args.org, args.repo, number)

        elif args.action == 'generate':
            # make a range of synthetic issues and PRs
            GM.generate = True
            if args.number:
                for number in args.number:
                    GM.get_issue(args.org, args.repo, number, itype='issue')
            else:
                for i in range(1, args.count):
                    ispr = bool(random.getrandbits(1))
                    if ispr or i == 1:
                        GM.get_issue(args.org, args.repo, i, itype='pull')
                    else:
                        GM.get_issue(args.org, args.repo, i, itype='issue')

        app.run(debug=True)
        #app.run(debug=False)
