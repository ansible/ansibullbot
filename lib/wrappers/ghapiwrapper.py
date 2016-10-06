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

def ratecheck():
    def decorator(func):
        def wrapper(*args, **kwargs):

	    #(Epdb) pp args
	    #(<lib.triagers.issuetriager.TriageIssues object at 0x7ff5c50e2a90>,)
            caller = None
            if args:
                caller = args[0]

            result = None
            retries = 0

            while True:

                # abort everything if we've hit the limit
                if retries > 10:
                    raise Exception('Max retries exceeded [%s|%s' % (retries, 10))

                try:
                    result = func(*args, **kwargs)
                    break

                except GithubException as ge:
                    print(ge)

                    if hasattr(ge, 'data'):
                        msg = str(ge.data)
                    else:
                        try:
                            data = ge[1]
                            msg = data.get('msg', '')
                        except Exception as e:
                            import epdb; epdb.st()

                    if 'blocked from content creation' in msg:
                        # https://github.com/octokit/octokit.net/issues/638
                        # only 20 creates(POSTs) per minute?
                        # maybe just try to sleep 5 minutes and retry?
                        print('POST limit reached. Sleeping 5m (%s)' % datetime.now())
                        time.sleep(60*5)
                    else:
                        # Attempt to use the caller's wait_for_rate function
                        if hasattr(caller, 'wait_for_rate_limit'):
                            caller.wait_for_rate_limit()
                        else:
                            import epdb; epdb.st()

                retries += 1

            return result
        return wrapper
    return decorator


class GithubWrapper(object):
    def __init__(self, gh):
        self.gh = gh
    def get_repo(self, repo_path):
        repo = RepoWrapper(self.gh, repo_path)
        return repo

    def get_current_time(self):
        return datetime.utcnow()

    @staticmethod
    def wait_for_rate_limit(githubobj=None):
        rl = githubobj.get_rate_limit()
        reset = rl.rate.reset
        now = datetime.utcnow()
        wait = (reset - now)
        wait = wait.total_seconds()
        if wait > 0:
            print('rate limit exceeded, sleeping %s minutes' % (wait / 60))
            time.sleep(wait)


class RepoWrapper(object):
    def __init__(self, gh, repo_path, verbose=True):

        self.gh = gh
        self.cachefile = os.path.join('~/.ansibullbot', 'cache', repo_path)
        self.cachefile = '%s/repo.pickle' % self.cachefile
        self.cachefile = os.path.expanduser(self.cachefile)
        self.cachedir = os.path.dirname(self.cachefile)
        self.updated_at_previous = None
        self.updated = False
        self.verbose = verbose

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

    def debug(self, msg=""):
        """Prints debug message if verbosity is given"""
        if self.verbose:
            print("Debug: " + msg)


    def save_repo(self):
        with open(self.cachefile, 'wb') as f:
            pickle.dump(self.repo, f)

    def get_issue(self, number):
        issue = self.load_issue(number)
        if issue:
            if issue.update():
                self.save_issue(issue)
        else:
            issue = self.repo.get_issue(number)
            self.save_issue(issue)
        return issue

    def get_pullrequest(self, number):
        pr = self.load_pullrequest(number)
        if pr:
            if pr.update():
                self.save_pr(pr)
        else:
            pr = self.repo.get_pull(number)
            self.save_pr(pr)
        return pr

    def get_labels(self):
        return self.load_update_fetch('labels')
    
    def get_issues(self, since=None, state='open', itype='issue'):

        if since:
            issues = self.repo.get_issues(since=since)
            issues = [x for x in issues]
            for issue in issues:
                self.save_issue(issue)
        else:

            # load all cached issues then update or fetch missing ...
            self.debug('loading cached issues')
            issues = self.load_issues()
            self.debug('fetching all issues')
            rissues = self.repo.get_issues()
            last_issue = rissues[0]

            self.debug('comparing cache against fetched')
            fetched = []
            expected = xrange(1, last_issue.number)
            for exp in expected:
                if self.is_missing(exp):
                    continue
                ci = next((i for i in issues if i.number == exp), None)

                # skip pull requests if requested
                if itype == 'issue' and ci:
                    if ci.pull_request:
                        #print('skipping %s' % ci.html_url)
                        continue
                #import epdb; epdb.st()

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
                            '''                            
                            print('rate limit exceeded, sleeping Xs')
                            rl = self.gh.get_rate_limit()
                            reset = rl.rate.reset
                            now = datetime.now()
                            wait = (reset - datetime.utcnow())
                            wait = wait.total_seconds()
                            print('rate limit exceeded, sleeping %s minutes' \
                                  % (wait / 60))
                            time.sleep(wait)
                            '''
                            GithubWrapper.wait_for_rate_limit(githubobj=None)
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

            self.debug('storing cache of repo')
            self.save_repo()

            if itype == 'issue':
                issues = [x for x in issues if not x.pull_request]

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

    def load_pullrequest(self, number):
        pfile = os.path.join(self.cachedir, 'issues', str(number), 'pullrequest.pickle')
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

    def save_pullrequest(self, issue):
        cfile = os.path.join(self.cachedir, 'issues', str(issue.number), 'pullrequest.pickle')
        cdir = os.path.dirname(cfile)
        if not os.path.isdir(cdir):
            os.makedirs(cdir)
        with open(cfile, 'wb') as f:
            pickle.dump(issue, f)

    def load_update_fetch(self, property_name):
        '''Fetch a get() property for an object'''

        edata = None
        events = []
        updated = None
        update = False
        write_cache = False
        self.repo.update()

        #import epdb; epdb.st()
        pfile = os.path.join(self.cachedir, '%s.pickle' % property_name)
        pdir = os.path.dirname(pfile)

        if not os.path.isdir(pdir):
            os.makedirs(pdir)

        if os.path.isfile(pfile):
            try:
                with open(pfile, 'rb') as f:
                    edata = pickle.load(f)
            except Exception as e:
                update = True
                write_cache = True

            # check the timestamp on the cache
            if edata:
                updated = edata[0]
                events = edata[1]
                if updated < self.repo.updated_at:
                    update = True
                    write_cache = True

        # pull all events if timestamp is behind or no events cached
        if update or not events:        
            write_cache = True
            updated = self.get_current_time()
            try:
                methodToCall = getattr(self.repo, 'get_' + property_name)
            except Exception as e:
                print(e)
                import epdb; epdb.st()
            events = [x for x in methodToCall()]

        if write_cache or not os.path.isfile(pfile):
            # need to dump the pickle back to disk
            edata = [updated, events]
            with open(pfile, 'wb') as f:
                pickle.dump(edata, f)

        return events

    def get_current_time(self):
        return datetime.utcnow()


