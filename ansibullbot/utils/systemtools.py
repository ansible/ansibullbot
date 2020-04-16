#!/usr/bin/env python

import copy
import os
import subprocess

from ansibullbot._text_compat import to_text


def run_command(cmd, cwd=None, env=None):
    if env:
        _env = copy.deepcopy(dict(os.environ))
        _env.update(env)
        env = copy.deepcopy(_env)
        for k,v in env.items():
            env[k] = str(v)
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env)
    (so, se) = p.communicate()
    return p.returncode, so, se


def fglob(directory, pattern, depth=1):
    cmd = u"find %s -maxdepth %s -type f -name '%s'" % (directory, depth, pattern)
    (rc, so, se) = run_command(cmd)
    filepaths = to_text(so).split(u'\n')
    filepaths = [x.strip() for x in filepaths if x.strip()]
    return filepaths
