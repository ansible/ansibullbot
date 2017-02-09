#!/usr/bin/env python

import datetime
import logging
import os
import re
from lib.utils.systemtools import *

from distutils.version import StrictVersion
from distutils.version import LooseVersion


def list_to_version(inlist, cast_string=True, reverse=True, binary=False):
    # [1,2,3] => "3.2.1"

    if type(inlist) == tuple:
        inlist = [x for x in inlist]

    if binary:
        # [2,1,0] => "1.1.0"
        for idx, x in enumerate(inlist):
            if x > 0:
                inlist[idx] = 1
    if cast_string:
        inlist = [str(x) for x in inlist]
    if reverse:
        inlist = [x for x in reversed(inlist)]
    vers = '.'.join(inlist)
    return vers


class AnsibleVersionIndexer(object):

    def __init__(self):
        self.modules = {}
        self.checkoutdir = '~/.ansibullbot/cache/ansible.version.checkout'
        self.checkoutdir = os.path.expanduser(self.checkoutdir)
        self.VALIDVERSIONS = None
        self.COMMITVERSIONS = None
        self.DATEVERSIONS = None

        if not os.path.isdir(self.checkoutdir):
            self.create_checkout()
        else:
            self.update_checkout()
        self._get_versions()

    def create_checkout(self):
        """checkout ansible"""
        cmd = "git clone http://github.com/ansible/ansible --recursive %s" \
            % self.checkoutdir
        (rc, so, se) = run_command(cmd)
        print str(so) + str(se)

    def update_checkout(self):
        """rebase + pull + update the checkout"""
        cmd = "cd %s ; git pull --rebase" % self.checkoutdir
        (rc, so, se) = run_command(cmd)
        print str(so) + str(se)
        cmd = "cd %s ; git submodule update --recursive" % self.checkoutdir
        (rc, so, se) = run_command(cmd)
        print str(so) + str(se)


    def _get_versions(self):
        self.VALIDVERSIONS = {}
        # get devel's version
        vpath = os.path.join(self.checkoutdir, 'VERSION')
        vpath = os.path.expanduser(vpath)
        devel_version = None
        with open(vpath, 'rb') as f:
            devel_version = f.read().strip().split()[0]
            self.VALIDVERSIONS[devel_version] = 'devel'

        # branches
        cmd = 'cd %s;' % self.checkoutdir
        cmd += 'git branch -a'
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        (so, se) = p.communicate()
        lines = [x.strip() for x in so.split('\n') if x.strip()]
        rlines = [x for x in lines if x.startswith('remotes/origin/release') \
                                  or x.startswith('remotes/origin/stable') ]
        rlines = [x.split('/')[-1] for x in rlines]
        rlines = [x.replace('release', '') for x in rlines]
        rlines = [x.replace('stable-', '') for x in rlines]
        for rline in rlines:
            if not rline in self.VALIDVERSIONS:
                self.VALIDVERSIONS[rline] = 'branch'

        # tags
        cmd = 'cd %s;' % self.checkoutdir
        cmd += 'git tag -l'
        p = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        (so, se) = p.communicate()
        lines = [x.strip() for x in so.split('\n') if x.strip()]
        rlines = [x.replace('v', '', 1) for x in lines]
        for rline in rlines:
            if not rline in self.VALIDVERSIONS:
                self.VALIDVERSIONS[rline] = 'tag'

    def is_valid_version(self, version):

        if not version:
            return False

        if not self.VALIDVERSIONS:
            self._get_versions()

        if version in self.VALIDVERSIONS:
            return True
        else:
            keys = [x for x in self.VALIDVERSIONS.keys()]
            keys = sorted(set(keys))
            for k in keys:
                if k.startswith(version) or version.startswith(k):
                    return True

        return False


    def strip_ansible_version(self, rawtext, logprefix=''):

        # any
        # all
        # all?
        # all ?
        # all recent releases
        # a55c6625d4771c44017fce1d487b38749b12b381 (latest dev)
        # ansible devel
        # devel
        # latest
        # latest devel branch
        # v2.0.0-0.9.rc4
        # N/A
        # NA
        # current head
        # master
        # not applicable
        # >2.0
        # - 1.8.2
        # - devel head f9c203feb68e224cd3d445568b39293f8a3d32ad
        # ansible@devel
        # 1.x
        # 2.x

        devel = ['devel', 'master', 'head', 'latest', 'all', 'all?', 'all ?', 'any',
                 'n/a', 'na', 'not applicable', 'latest devel',
                 'latest devel branch', 'ansible devel', '', 'future',
                 'git version', 'ansible@devel', 'all recent releases']

        if not self.VALIDVERSIONS:
            self._get_versions()

        aversion = False

        rawtext = rawtext.replace('`', '')
        rawtext = rawtext.strip()
        rawtext = rawtext.lower()
        rawlines = rawtext.split('\n')
        rawlines = [x.strip() for x in rawlines]

        # exit early for "devel" variations ...
        if rawtext in devel:
            return 'devel'

        # handle 1.x/2.x globs
        xver = re.compile('^-?[1-9].x')
        if len(rawlines) == 1:
            if xver.match(rawlines[0]):
                major_ver = rawlines[0].split('.')[0]

                # Get the highest minor version for this major
                cversions = reversed(sorted(self.VALIDVERSIONS.keys()))
                for cver in cversions:
                    if cver[0] == major_ver:
                        aversion = cver
                        break
                if aversion:
                    return aversion

        xver = re.compile('^-?[1-9].[1-9].x')
        if len(rawlines) == 1:
            if xver.match(rawlines[0]):
                major_ver = rawlines[0].split('.')[0]
                minor_ver = rawlines[0].split('.')[1]

                # Get the highest minor version for this major
                cversions = reversed(sorted(self.VALIDVERSIONS.keys()))
                for cver in cversions:
                    if cver[0:3] == (major_ver + '.' + minor_ver):
                        aversion = cver
                        break
                if aversion:
                    return aversion

        # check for copy/paste from --version output
        for idx,x in enumerate(rawlines):
            if len(rawlines) < (idx+2):
                continue
            if x.startswith('ansible') and \
                (rawlines[idx+1].startswith('config file') \
                or rawlines[idx+1].startswith('configured module search path')):
                parts = x.replace(')', '').split()
                aversion = parts[1]

                # is this a checkout with a hash? ...
                if len(parts) > 3:
                    ahash = parts[3]
                elif len(parts) > 2:
                    # ['ansible', '2.2.0.0', 'rc1']
                    pass
                return aversion

        # try to find a vstring ...
        pidx = rawtext.find('.')
        if pidx > -1:
            fver = ''
            # get chars to the end of the vstring ...
            for char in rawtext[pidx:]:
                if char == ' ' or char == '\n' or char == '\r' \
                    or (not char.isalnum() and char != '.'):
                    break
                else:
                    fver += char
            head = rawtext[:pidx]
            head = head[::-1]
            # get chars to the beginning of the vstring ...
            for char in head:
                if char == ' ' or char == '\n' or char == '\r' \
                    or (not char.isalnum() and char != '.'):
                    break
                else:
                    fver = char + fver
            if fver[0] == 'v':
                fver=fver[1:]
            if fver:
                sver = None
                lver = None

                try:
                    sver = StrictVersion(fver)
                except Exception as se:
                    pass

                try:
                    lver = LooseVersion(fver)
                except Exception as le:
                    pass

                if sver:
                    return fver
                elif lver and fver[0].isdigit():
                    return fver

        lines = rawtext.split('\n')
        orig_lines = lines
        lines = [x.strip() for x in lines if x.strip()]
        lines = [x for x in lines if not x.startswith('config')]
        lines = [x for x in lines if not x.startswith('<')]
        lines = [x for x in lines if not x.startswith('-')]
        lines = [x for x in lines if not x.startswith('lib')]
        for idx,x in enumerate(lines):
            #if x.startswith('ansible'):
            #    x = x.replace('ansible', '').strip()
            if "'" in x:
                x = x.replace("'", '').strip()
            if '"' in x:
                x = x.replace('"', '').strip()
            if '`' in x:
                x = x.replace('`', '').strip()
            if ',' in x:
                x = x.replace(',', '').strip()
            if '*' in x:
                x = x.replace('*', '').strip()
            if ')' in x:
                x = x.replace(')', '').strip()
            #if 'v' in x:
            #    x = x.replace('v', '', 1).strip()
            lines[idx] = x
        lines = [x.strip() for x in lines if x.strip()]
        lines = [x for x in lines if x.startswith('ansible') or x[0].isdigit() or x[0] == 'v']

        # https://github.com/ansible/ansible-modules-extras/issues/809
        #   false positives from this issue ...
        lines = [x for x in lines if not 'versions: []' in x]

        # try to narrow down to a single line
        if len(lines) > 1:
            candidate = None
            for x in lines:
                pidx = x.find('.')
                if pidx == -1:
                    continue
                if (len(x) - 1) < (pidx+1):
                    continue
                if not x[pidx+1].isdigit():
                    continue
                if (x.startswith('ansible') or x[0].isdigit()) and '.' in x:
                    candidate = x
                    break
            if candidate:
                lines = [candidate]

        if len(lines) > 0:
            try:
                StrictVersion(lines[0])
                aversion = lines[0]
            except Exception as e:

                words = lines[0].split()
                words = [x.strip() for x in words if x.strip()]
                words = [x for x in words if x != 'stable']
                words = [x for x in words if x != 'ansible']
                words = [x for x in words if x != 'ansible-doc']
                words = [x for x in words if x != 'ansible-playbook']
                if not words:
                    print logprefix + "NO VERSIONABLE WORDS!!"
                    pass
                else:

                    if words[0].startswith('ansible-'):
                        words[0] = words[0].replace('ansible-', '')

                    if words[0][0] == 'v':
                        words[0] = words[0][1:]
                    characters = words[0].split('.')
                    digits = [x.isdigit() for x in characters]
                    digits = sorted(set(digits))
                    if digits == [True]:
                        try:
                            aversion = words[0]
                        except Exception as e:
                            logging.error(e)
                            logging.error('breakpoint!')
                            import epdb; epdb.st()
                    elif characters[0].isdigit():
                        aversion = words[0]
                    else:
                        print logprefix + "INVALID VER STRING !!!"
                        print logprefix + 'Exception: ' + str(e)
                        for line in lines:
                            print logprefix + line

        if not aversion:
            pass

        return aversion


    def ansible_version_by_commit(self, commithash, config=None):

        # $ git branch --contains e620fed755a9c7e07df846b7deb32bbbf3164ac7
        # * devel

        #$ git branch -r --contains 6d9949698bd6a5693ef64cfde845c029f0e02b91 | egrep -e 'release' -e 'stable' | head
        #  origin/release1.5.0
        #  origin/release1.5.1
        #  origin/release1.5.2
        #  origin/release1.5.3
        #  origin/release1.5.4
        #  origin/release1.5.5
        #  origin/release1.6.0
        #  origin/release1.6.1
        #  origin/release1.6.10
        #  origin/release1.6.2

        '''
        # make sure the checkout cache is still valid
        self.update_checkout()
        '''

        aversion = None

        if not self.COMMITVERSIONS:
            self.COMMITVERSIONS = {}

        if commithash in self.COMMITVERSIONS:
            aversion = self.COMMITVERSIONS[commithash]
        else:
            # get devel's version
            vpath = os.path.join(self.checkoutdir, 'VERSION')
            vpath = os.path.expanduser(vpath)
            devel_version = None
            with open(vpath, 'rb') as f:
                devel_version = f.read().strip().split()[0]

            cmd = 'cd %s;' % self.checkoutdir
            cmd += 'git branch -r --contains %s' % commithash
            (rc, so, se) = run_command(cmd)
            lines = [x.strip() for x in so.split('\n') if x.strip()]

            rlines = [x for x in lines if x.startswith('origin/release') \
                                      or x.startswith('origin/stable') ]
            rlines = [x.split('/')[-1] for x in rlines]
            rlines = [x.replace('release', '') for x in rlines]
            rlines = [x.replace('stable-', '') for x in rlines]

            if rc != 0:
                logging.error("rc != 0")
                logging.error('breakpoint!')
                import epdb; epdb.st()

            if len(rlines) > 0:
                aversion = rlines[0]
            else:
                if 'HEAD' in lines[0] or lines[0].endswith('/devel'):
                    '''
                    cmd = 'cd %s;' % self.checkoutdir
                    cmd += 'git branch -a | fgrep -e release -e stable | tail -n 1'
                    (rc, so, se) = run_command(cmd)
                    cver = so.strip()
                    cver = cver.replace('remotes/origin/stable-', '')
                    cver = cver.replace('remotes/upstream/stable-', '')
                    cver = cver.replace('remotes/origin/release', '')
                    cver = cver.replace('remotes/upstream/release', '')
                    assert cver, "cver is null"
                    assert cver[0].isdigit(), "cver[0] is not digit: %s" % cver
                    aversion = cver
                    '''
                    aversion = devel_version
                else:
                    logging.error("WTF!? ...")
                    logging.error('breakpoint!')
                    import epdb; epdb.st()

            self.COMMITVERSIONS[commithash] = aversion

        return aversion


    def ansible_version_by_date(self, dateobj, devel=False):

        if not self.DATEVERSIONS:
            self.DATEVERSIONS = []
            cmd = 'cd %s;' % self.checkoutdir
            cmd += 'git log --date=short --pretty=format:"%ad;%H"'
            (rc, so, se) = run_command(cmd)
            lines = [x.strip() for x in so.split('\n') if x.strip()]
            for x in lines:
                parts = x.split(';')
                self.DATEVERSIONS.append(parts)

        last_commit_date = self.DATEVERSIONS[0][0]
        last_commit_date = datetime.datetime.strptime(
            last_commit_date,
            '%Y-%m-%d'
        )

        # use last commit version if older than incoming date
        if dateobj >= last_commit_date:
            acommit = self.DATEVERSIONS[0][1]
        else:
            acommit = None
            datestr = str(dateobj).split()[0]
            for dv in reversed(self.DATEVERSIONS):
                if dv[0] == datestr:
                    accommit = dv[1]
                    break
            if not acommit:
                datestr = '-'.join(datestr.split('-')[0:2])
                for dv in self.DATEVERSIONS:
                    dvs = '-'.join(dv[0].split('-')[0:2])
                    if dvs == datestr:
                        acommit = dv[1]
                        break

        aversion = None
        if acommit:
            aversion = self.ansible_version_by_commit(acommit)

        return aversion


    def get_major_minor(self, vstring):
        '''Return an X.Y version'''
        lver = LooseVersion(vstring)
        rval = '.'.join([str(x) for x in lver.version[0:2]])
        return rval
