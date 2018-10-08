#!/usr/bin/env python

import datetime
import logging
import os
import re
import subprocess

from ansibullbot._text_compat import to_text
from ansibullbot.utils.systemtools import run_command

from distutils.version import StrictVersion
from distutils.version import LooseVersion

import ansibullbot.constants as C


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
        inlist = [to_text(x) for x in inlist]
    if reverse:
        inlist = [x for x in reversed(inlist)]
    vers = u'.'.join(inlist)
    return vers


class AnsibleVersionIndexer(object):

    def __init__(self, checkoutdir):
        self.modules = {}
        self.checkoutdir = checkoutdir
        self.VALIDVERSIONS = None
        self.COMMITVERSIONS = None
        self.DATEVERSIONS = None

        self._get_versions()

    def _get_devel_version(self):
        # get devel's version
        vpath = os.path.join(self.checkoutdir, u'VERSION')
        vpath = os.path.expanduser(vpath)
        devel_version = None

        if os.path.isfile(vpath):
            with open(vpath, 'rb') as f:
                devel_version = f.read().strip().split()[0]
                self.VALIDVERSIONS[devel_version] = u'devel'
        else:
            # __version__ = '2.6.0dev0'
            vpath = os.path.join(self.checkoutdir, u'lib/ansible/release.py')
            with open(vpath, 'r') as f:
                flines = f.readlines()
            for line in flines:
                line = line.strip()
                if line.startswith(u'__version__'):
                    devel_version = line.split(u'=')[-1].strip()
                    devel_version = devel_version.replace(u"'", u'')
                    devel_version = devel_version.replace(u'"', u'')
                    break

        return devel_version

    def _get_versions(self):
        self.VALIDVERSIONS = {}

        # get devel's version
        devel_version = self._get_devel_version()

        # branches
        cmd = u'cd %s;' % self.checkoutdir
        cmd += u'git branch -a'
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        (so, se) = p.communicate()
        lines = [x.strip() for x in so.split(b'\n') if x.strip()]
        rlines = [
            x for x in lines
            if x.startswith((b'remotes/origin/release', b'remotes/origin/stable'))
        ]
        rlines = [x.split(b'/')[-1] for x in rlines]
        rlines = [x.replace(b'release', b'') for x in rlines]
        rlines = [x.replace(b'stable-', b'') for x in rlines]
        for rline in rlines:
            if rline not in self.VALIDVERSIONS:
                self.VALIDVERSIONS[rline] = u'branch'

        # tags
        cmd = u'cd %s;' % self.checkoutdir
        cmd += u'git tag -l'
        p = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        (so, se) = p.communicate()
        lines = [x.strip() for x in so.split(b'\n') if x.strip()]
        rlines = [x.replace(b'v', b'', 1) for x in lines]
        for rline in rlines:
            if rline not in self.VALIDVERSIONS:
                self.VALIDVERSIONS[rline] = u'tag'

    def is_valid_version(self, version):

        if not version:
            return False

        if not self.VALIDVERSIONS:
            self._get_versions()

        if version in self.VALIDVERSIONS:
            return True
        else:
            keys = (x for x in self.VALIDVERSIONS.keys())
            keys = (to_text(k) for k in sorted(set(keys)))
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

        devel = [u'devel', u'master', u'head', u'latest', u'all', u'all?', u'all ?', u'any',
                 u'n/a', u'na', u'not applicable', u'latest devel',
                 u'latest devel branch', u'ansible devel', u'', u'future',
                 u'git version', u'ansible@devel', u'all recent releases']

        if not self.VALIDVERSIONS:
            self._get_versions()

        aversion = False

        rawtext = rawtext.replace(u'`', u'')
        rawtext = rawtext.strip()
        rawtext = rawtext.lower()
        rawlines = rawtext.split(u'\n')
        rawlines = [x.strip() for x in rawlines]

        # exit early for "devel" variations ...
        if rawtext in devel:
            return u'devel'

        # handle 1.x/2.x globs
        xver = re.compile(u'^-?[1-9].x')
        if len(rawlines) == 1:
            if xver.match(rawlines[0]):
                major_ver = rawlines[0].split(u'.')[0]

                # Get the highest minor version for this major
                cversions = reversed(sorted(self.VALIDVERSIONS.keys()))
                for cver in cversions:
                    if cver[0] == major_ver:
                        aversion = cver
                        break
                if aversion:
                    return aversion

        xver = re.compile(u'^-?[1-9].[1-9].x')
        if len(rawlines) == 1:
            if xver.match(rawlines[0]):
                major_ver = rawlines[0].split(u'.')[0]
                minor_ver = rawlines[0].split(u'.')[1]

                # Get the highest minor version for this major
                cversions = reversed(sorted(self.VALIDVERSIONS.keys()))
                for cver in cversions:
                    if cver[0:3] == (major_ver + u'.' + minor_ver):
                        aversion = cver
                        break
                if aversion:
                    return aversion

        # check for copy/paste from --version output
        for idx, x in enumerate(rawlines):
            if len(rawlines) < (idx+2):
                continue
            if x.startswith(u'ansible') and \
                (rawlines[idx+1].startswith(u'config file') or
                 rawlines[idx+1].startswith(u'configured module search path')):
                parts = x.replace(u')', u'').split()
                aversion = parts[1]

                # is this a checkout with a hash? ...
                if len(parts) > 3:
                    pass
                elif len(parts) > 2:
                    # ['ansible', '2.2.0.0', 'rc1']
                    pass
                return aversion

        # try to find a vstring ...
        pidx = rawtext.find(u'.')
        if pidx > -1:
            fver = u''
            # get chars to the end of the vstring ...
            for char in rawtext[pidx:]:
                if char == u' ' or char == u'\n' or char == u'\r' \
                        or (not char.isalnum() and char != u'.'):
                    break
                else:
                    fver += char
            head = rawtext[:pidx]
            head = head[::-1]
            # get chars to the beginning of the vstring ...
            for char in head:
                if char == u' ' or char == u'\n' or char == u'\r' \
                        or (not char.isalnum() and char != u'.'):
                    break
                else:
                    fver = char + fver
            if fver[0] == u'v':
                fver = fver[1:]
            if fver:
                sver = None
                lver = None

                try:
                    sver = StrictVersion(fver)
                except Exception:
                    pass

                try:
                    lver = LooseVersion(fver)
                except Exception:
                    pass

                if sver:
                    return fver
                elif lver and fver[0].isdigit():
                    return fver

        lines = rawtext.split(u'\n')
        lines = [x.strip() for x in lines if x.strip()]
        lines = [x for x in lines if not x.startswith(u'config')]
        lines = [x for x in lines if not x.startswith(u'<')]
        lines = [x for x in lines if not x.startswith(u'-')]
        lines = [x for x in lines if not x.startswith(u'lib')]
        for idx, x in enumerate(lines):
            if u"'" in x:
                x = x.replace(u"'", u'').strip()
            if u'"' in x:
                x = x.replace(u'"', u'').strip()
            if u'`' in x:
                x = x.replace(u'`', u'').strip()
            if u',' in x:
                x = x.replace(u',', u'').strip()
            if u'*' in x:
                x = x.replace(u'*', u'').strip()
            if u')' in x:
                x = x.replace(u')', u'').strip()
            lines[idx] = x
        lines = [x.strip() for x in lines if x.strip()]
        lines = [x for x in lines if x.startswith(u'ansible') or x[0].isdigit() or x[0] == u'v']

        # https://github.com/ansible/ansible-modules-extras/issues/809
        #   false positives from this issue ...
        lines = [x for x in lines if u'versions: []' not in x]

        # try to narrow down to a single line
        if len(lines) > 1:
            candidate = None
            for x in lines:
                pidx = x.find(u'.')
                if pidx == -1:
                    continue
                if (len(x) - 1) < (pidx+1):
                    continue
                if not x[pidx+1].isdigit():
                    continue
                if (x.startswith(u'ansible') or x[0].isdigit()) and u'.' in x:
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
                words = [x for x in words if x != u'stable']
                words = [x for x in words if x != u'ansible']
                words = [x for x in words if x != u'ansible-doc']
                words = [x for x in words if x != u'ansible-playbook']
                if not words:
                    print(logprefix + u"NO VERSIONABLE WORDS!!")
                    pass
                else:

                    if words[0].startswith(u'ansible-'):
                        words[0] = words[0].replace(u'ansible-', u'')

                    if words[0][0] == u'v':
                        words[0] = words[0][1:]
                    characters = words[0].split(u'.')
                    digits = [x.isdigit() for x in characters]
                    digits = sorted(set(digits))
                    if digits == [True]:
                        try:
                            aversion = words[0]
                        except Exception as e:
                            logging.error(e)
                            if C.DEFAULT_BREAKPOINTS:
                                logging.error(u'breakpoint!')
                                import epdb; epdb.st()
                            else:
                                raise Exception(u'indexerror: %s' % e)
                    elif characters[0].isdigit():
                        aversion = words[0]
                    else:
                        print(logprefix + u"INVALID VER STRING !!!")
                        print(logprefix + u'Exception: ' + to_text(e))
                        for line in lines:
                            print(logprefix + line)

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
            devel_version = self._get_devel_version()

            cmd = u'cd %s;' % self.checkoutdir
            cmd += u'git branch -r --contains %s' % commithash
            (rc, so, se) = run_command(cmd)
            lines = (x.strip() for x in to_text(so).split(u'\n'))
            lines = list(filter(bool, lines))

            rlines = (x for x in lines
                      if x.startswith((u'origin/release', u'origin/stable')))
            rlines = (x.split(u'/')[-1] for x in rlines)
            rlines = (x.replace(u'release', u'') for x in rlines)
            rlines = [x.replace(u'stable-', u'') for x in rlines]

            if rc != 0:
                logging.error(u"rc != 0")
                if C.DEFAULT_BREAKPOINTS:
                    logging.error(u'breakpoint!')
                    import epdb; epdb.st()
                else:
                    raise Exception(u'bad returncode')

            if len(rlines) > 0:
                aversion = rlines[0]
            else:
                if u'HEAD' in lines[0] or lines[0].endswith(u'/devel'):
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
                    logging.error(u"WTF!? ...")
                    if C.DEFAULT_BREAKPOINTS:
                        logging.error(u'breakpoint!')
                        import epdb; epdb.st()
                    else:
                        raise Exception(u'HEAD not found')

            self.COMMITVERSIONS[commithash] = aversion

        return aversion

    def version_by_date(self, dateobj, devel=False):

        if not self.DATEVERSIONS:
            self.DATEVERSIONS = []
            cmd = u'cd %s;' % self.checkoutdir
            cmd += u'git log --date=short --pretty=format:"%ad;%H"'
            (rc, so, se) = run_command(cmd)
            lines = (x.strip() for x in to_text(so).split(u'\n'))
            lines = filter(bool, lines)
            for x in lines:
                parts = x.split(u';')
                self.DATEVERSIONS.append(parts)

        last_commit_date = self.DATEVERSIONS[0][0]
        last_commit_date = datetime.datetime.strptime(
            last_commit_date,
            u'%Y-%m-%d'
        )

        # use last commit version if older than incoming date
        if dateobj >= last_commit_date:
            acommit = self.DATEVERSIONS[0][1]
        else:
            acommit = None
            datestr = to_text(dateobj).split()[0]
            for dv in reversed(self.DATEVERSIONS):
                if dv[0] == datestr:
                    break
            if not acommit:
                datestr = u'-'.join(datestr.split(u'-')[0:2])
                for dv in self.DATEVERSIONS:
                    dvs = u'-'.join(dv[0].split(u'-')[0:2])
                    if dvs == datestr:
                        acommit = dv[1]
                        break

        aversion = None
        if acommit:
            aversion = self.ansible_version_by_commit(acommit)

        return aversion

