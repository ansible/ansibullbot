#!/usr/bin/env python

import subprocess


def run_command(cmd, cwd=None):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
    (so, se) = p.communicate()
    return p.returncode, so, se


def fglob(directory, pattern, depth=1):
    cmd = "find %s -maxdepth %s -type f -name '%s'" % (directory, depth, pattern)
    (rc, so, se) = run_command(cmd)
    filepaths = so.split('\n')
    filepaths = [x.strip() for x in filepaths if x.strip()]
    return filepaths
