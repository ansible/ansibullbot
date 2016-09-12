#!/usr/bin/env python

from __future__ import print_function

import github
from github.GithubException import GithubException
import glob
import pickle
import operator
import os
import socket
import sys
import time
from datetime import datetime

class GithubWrapper(object):
    def __init__(self, gh):
        self.gh = gh
    def get_repo(self, repo_path):
        repo = RepoWrapper(self.gh, repo_path)
        return repo

class RepoWrapper(object):
    def __init__(self, gh, repo_path):

        self.gh = gh
        self.cachefile = os.path.join('~/.ansibullbot', 'cache', repo_path)
        self.cachefile = '%s/repo.pickle' % self.cachefile
        self.cachefile = os.path.expanduser(self.cachefile)
        self.cachedir = os.path.dirname(self.cachefile)
        self.updated_at_previous = None
        self.updated = False

        if not os.path.isdir(self.cachedir):
            os.makedirs(self.cachedir)
        if os.path.isfile(self.cachefile):
            with open(self.cachefile, 'rb') as f:
                self.repo = pickle.load(f)
            self.updated_at_previous = self.repo.updated_at
            self.updated = self.repo.update()
        else:
            self.repo = self.gh.get_repo(repo_path)
            self.save_repo()

    def save_repo(self):
        with open(self.cachefile, 'wb') as f:
            pickle.dump(self.repo, f)

    def get_issue(self, number):
        issue = self.load_issue(number)
        if issue:
            issue.update()
        else:
            issue = self.repo.get_issue(exp)
        self.save_issue(issue)
        #import epdb; epdb.st()
        return issue
    
    def get_issues(self, since=None, state='open'):

        if since:
            issues = self.repo.get_issues(since=since)
            issues = [x for x in issues]
            for issue in issues:
                self.save_issue(issue)
        else:

            # load all cached issues then update or fetch missing ...

            issues = self.load_issues()
            rissues = self.repo.get_issues()
            last_issue = rissues[0]

            fetched = []
            expected = xrange(1, last_issue.number)
            for exp in expected:
                if self.is_missing(exp):
                    continue
                ci = next((i for i in issues if i.number == exp), None)

                retry = True
                while retry:                
                    try:
                        if not ci:
                            print('%s was not cached' % exp)
                            issue = self.repo.get_issue(exp)
                            issues.append(issue)
                            self.save_issue(issue)
                            retry = False
                        else:
                            # update and save [only if open]
                            if ci.state == 'open':
                                if ci.update():
                                    self.save_issue(ci)
                            retry = False

                    except socket.timeout as e:
                        #import epdb; epdb.st()
                        print('socket timeout, sleeping 10s')
                        time.sleep(10)

                    except IndexError as e:
                        #self.set_missing(exp)
                        print('index error, sleeping 10s')
                        time.sleep(10)

                    except GithubException as e:
                        if 'rate limit exceeded' in e[1]['message']:
                            retry = True
                            print('rate limit exceeded, sleeping Xs')
                            rl = self.gh.get_rate_limit()
                            reset = rl.rate.reset
                            now = datetime.now()
                            wait = (reset - datetime.utcnow())
                            wait = wait.total_seconds()
                            print('rate limit exceeded, sleeping %s minutes' \
                                  % (wait / 60))
                            time.sleep(wait)
                        elif e[1]['message'] == 'Not Found':
                            self.set_missing(exp)
                            retry = False
                        else:
                            print(e)
                            import epdb; epdb.st()

                    except Exception as e:
                        print(e)
                        print("could not fetch %s" % exp)
                        import epdb; epdb.st()

            self.save_repo()

            if state == 'open':
                issues = [x for x in issues if x.state == 'open']

            # sort in reverse numerical order
            issues.sort(key = lambda x: x.number, reverse=True)

        return issues

    def is_missing(self, number):
        mfile = os.path.join(self.cachedir, 'issues', str(number), 'missing')
        if os.path.isfile(mfile):
            return True
        else:
            return False

    def set_missing(self, number):
        mfile = os.path.join(self.cachedir, 'issues', str(number), 'missing')
        mdir = os.path.dirname(mfile)
        if not os.path.isdir(mdir):
            os.makedirs(mdir)
        with open(mfile, 'wb') as f:
            f.write('\n')

    def load_issues(self, state='open'):
        issues = []
        gfiles = glob.glob('%s/issues/*/issue.pickle' % self.cachedir)
        for gf in gfiles:
            with open(gf, 'rb') as f:
                issue = pickle.load(f)
                #if state == 'open' and issue.state == 'open':
                #    issues.append(issue)
                issues.append(issue)
        return issues

    def load_issue(self, number):
        pfile = os.path.join(self.cachedir, 'issues', str(number), 'issue.pickle')
        if os.path.isfile(pfile):
            with open(pfile, 'rb') as f:
                issue = pickle.load(f)
            return issue
        else:
            return False


    def save_issues(self, issues):
        for issue in issues:
            self.save_issue(issue)

    def save_issue(self, issue):
        cfile = os.path.join(self.cachedir, 'issues', str(issue.number), 'issue.pickle')
        cdir = os.path.dirname(cfile)
        if not os.path.isdir(cdir):
            os.makedirs(cdir)
        with open(cfile, 'wb') as f:
            pickle.dump(issue, f)



