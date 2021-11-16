import os
import re
import typing as t

from ansibullbot._text_compat import to_text
from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.timetools import strip_time_safely


# from distutils.version.StrictVersion
_version_re = re.compile(r'^(\d+) \. (\d+) (\. (\d+))? ([ab](\d+))?$',
                        re.VERBOSE | re.ASCII)


def _is_valid_version(vstring):
    match = _version_re.match(vstring)
    if not match:
        return False
    return True


def get_version_major_minor(version: str) -> str:
    return version.rsplit('.', 2)[0]


class AnsibleVersionIndexer:
    def __init__(self, checkoutdir):
        self.checkoutdir = checkoutdir
        self.valid_versions = self._get_valid_versions()
        self.commit_versions_cache = {}
        self._commits_by_date = None

    @property
    def commits_by_date(self) -> None:
        if self._commits_by_date is not None:
            return self._commits_by_date

        _, stdout, _ = run_command('cd {};git log --date=short --pretty=format:"%ad;%H"'.format(self.checkoutdir))
        self._commits_by_date = [x.strip().split(';') for x in to_text(stdout).splitlines() if x.strip()]
        return self._commits_by_date

    def _get_devel_version(self) -> str:
        # __version__ = '2.13.0dev0'
        with open(os.path.join(self.checkoutdir, 'lib/ansible/release.py')) as f:
            lines = f.readlines()
        for line in lines:
            if line.strip().startswith('__version__'):
                return line.split('=')[-1].strip().replace("'", '').replace('"', '')

        raise ValueError('devel version not found in lib/ansible/release.py')

    def _get_valid_versions(self) -> t.Dict[str, str]:
        valid_versions = {}
        _, stdout, _ = run_command('cd %s;git branch -a' % self.checkoutdir)
        lines = [
            x.strip().split('/')[-1].replace('release', '').replace('stable-', '')
            for x in to_text(stdout).splitlines()
            if x.strip().startswith(('remotes/origin/release', 'remotes/origin/stable'))
        ]
        for line in lines:
            if line not in valid_versions:
                valid_versions[line] = 'branch'

        _, stdout, _ = run_command('cd %s;git tag -l' % self.checkoutdir)
        lines = [x.strip().replace('v', '', 1) for x in to_text(stdout).splitlines() if x.strip()]
        for line in lines:
            if line not in valid_versions:
                valid_versions[line] = 'tag'

        return valid_versions

    def is_valid_version(self, version: str) -> bool:
        if version in self.valid_versions:
            return True

        for valid_version in self.valid_versions.keys():
            if valid_version.startswith(version) or version.startswith(valid_version):
                return True

        return False

    def strip_ansible_version(self, rawtext):
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
        if rawtext is None:
            return 'devel'

        devel = ['devel', 'master', 'head', 'latest', 'all', 'all?', 'all ?', 'any',
                 'n/a', 'na', 'not applicable', 'latest devel',
                 'latest devel branch', 'ansible devel', '', 'future',
                 'git version', 'ansible@devel', 'all recent releases']

        if rawtext in devel:
            return 'devel'

        rawtext = rawtext.replace('`', '').strip().lower()
        rawlines = [x.strip() for x in rawtext.split('\n')]

        # handle 1.x/2.x globs
        xver = re.compile('^-?[1-9].x')
        if len(rawlines) == 1:
            if xver.match(rawlines[0]):
                major_ver = rawlines[0].split('.')[0]

                # Get the highest minor version for this major
                for cver in reversed(sorted(self.valid_versions.keys())):
                    if cver[0] == major_ver:
                        return cver

        xver = re.compile('^-?[1-9].[1-9].x')
        if len(rawlines) == 1:
            if xver.match(rawlines[0]):
                major_ver = rawlines[0].split('.')[0]
                minor_ver = rawlines[0].split('.')[1]

                # Get the highest minor version for this major
                for cver in reversed(sorted(self.valid_versions.keys())):
                    if cver[0:3] == (major_ver + '.' + minor_ver):
                        return cver

        # check for copy/paste from --version output
        for idx, x in enumerate(rawlines):
            if len(rawlines) < (idx+2):
                continue
            if x.startswith('ansible') and \
                    (rawlines[idx+1].startswith(('config file', 'configured module search path'))):
                parts = x.replace(')', '').replace('[', '').replace(']', '').split()
                aversion = parts[1]

                if len(parts) > 2:
                    if aversion == 'core':
                        aversion = parts[2]
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
                fver = fver[1:]
            if fver:
                if fver[0].isdigit():
                    return fver
                valid = False
                try:
                    valid = _is_valid_version(fver)
                except ValueError:
                    pass
                if valid:
                    return fver

        lines = [x.strip() for x in rawtext.split('\n') if x.strip()]
        lines = [x for x in lines if not x.startswith(('config', '<', '-', 'lib'))]
        for idx, x in enumerate(lines):
            lines[idx] = x.translate(str.maketrans({"'": '', '"': '', '`': '', ',': '', '*': '', ')': ''}))
        lines = [x.strip() for x in lines if x.strip()]
        lines = [x for x in lines if x.startswith('ansible') or x[0].isdigit() or x[0] == 'v']

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
            if _is_valid_version(lines[0]):
                return lines[0]
            else:
                words = [x.strip() for x in lines[0].split() if x.strip()]
                words = [x for x in words if x not in ('stable', 'ansible', 'ansible-doc', 'ansible-playbook')]
                if words:
                    if words[0].startswith('ansible-'):
                        words[0] = words[0].replace('ansible-', '')
                    if words[0][0] == 'v':
                        words[0] = words[0][1:]
                    characters = words[0].split('.')
                    digits = sorted(set((x.isdigit() for x in characters)))
                    aversion = None
                    if digits == [True] or characters[0].isdigit():
                        aversion = words[0]
                    return aversion

    def version_by_commit(self, commithash: str) -> str:
        """
        $ git branch --contains e620fed755a9c7e07df846b7deb32bbbf3164ac7
        * devel
        $ git branch -r --contains 6d9949698bd6a5693ef64cfde845c029f0e02b91 | egrep -e 'release' -e 'stable' | head
         origin/release1.5.0
         origin/release1.5.1
         ...
        """
        if commithash in self.commit_versions_cache:
            return self.commit_versions_cache[commithash]

        rc, stdout, _ = run_command('cd %s;git branch -r --contains %s' % (self.checkoutdir, commithash))
        if rc != 0:
            raise Exception("rc == %d from cmd = '%s'" % (rc, cmd))

        branches = [x.strip() for x in to_text(stdout).splitlines()]

        for branch in branches:
            if branch.startswith(('origin/release', 'origin/stable')):
                version = branch.split('/')[-1].replace('release', '').replace('stable-', '')
                break
        else:
            for branch in branches:
                if 'HEAD' in branch or branch.endswith('/devel'):
                    version = self._get_devel_version()
                    break
            else:
                raise ValueError('HEAD not found')

        self.commit_versions_cache[commithash] = version

        return version

    def version_by_date(self, dateobj) -> str:
        last_commit_date = strip_time_safely(self.commits_by_date[0][0])

        if dateobj >= last_commit_date:
            commit = self.commits_by_date[0][1]
        else:
            commit = None
            datestr = str(dateobj).split()[0]
            for dv in reversed(self.commits_by_date):
                if dv[0] == datestr:
                    commit = dv[1]
                    break
            else:
                datestr = '-'.join(datestr.split('-')[0:2])
                for dv in self.commits_by_date:
                    dvs = '-'.join(dv[0].split('-')[0:2])
                    if dvs == datestr:
                        commit = dv[1]
                        break

        if commit:
            return self.version_by_commit(commit)

    def version_by_issue(self, iw) -> str:
        version = self.strip_ansible_version(iw.template_data.get('ansible version', ''))

        if not version or version == 'devel':
            version = self.version_by_date(iw.instance.created_at)

        if version and version.endswith('.'):
            version += '0'

        if version and version.endswith('.x'):
            version = self.strip_ansible_version(version)

        if self.is_valid_version(version):
            return version

        for comment in iw.history.get_user_comments(iw.submitter):
            found_version = self.strip_ansible_version(comment['body'])
            if self.is_valid_version(found_version):
                return found_version

        raise ValueError('version by issue %d not found' % iw.number)
