#!/usr/bin/env python

import json
import glob
import os
import shutil

gpath = '~/.ansibullbot/cache/shippable.runs/*/results.json'
gpath = os.path.expanduser(gpath)
jfiles = glob.glob(gpath)

for jf in jfiles:
    candidate = False
    with open(jf, 'rb') as f:
        jdata = json.load(f)
    for x in jdata:
        candidate = False
        if x.get('path') != '/testresults.json':
            continue
        if not x.get('testresults'):
            continue
        trs = x.get('testresults')
        for tr in trs:
            if not tr.get('failureDetails'):
                continue
            fds = [fd for fd in tr['failureDetails']
                   if fd['className'] == 'sanity']
            if not fds:
                continue

            jfdir = os.path.dirname(jf)
            trfile = os.path.join(jfdir, x.get('job_id'), 'testresults.json')

            rfiles = glob.glob(
                '/home/jtanner/.ansibullbot/cache/shippable.runs/.raw/*%s*'
                % x.get('job_id')
            )

            print(jf)
            print(trfile)
            print('\t%s %s' % (x.get('run_id'), x.get('job_id')))
            #print('\t%s' % (x.get('url')))
            print('\t%s' % (tr['job_url']))
            for rf in rfiles:
                print('\t%s' % rf)
                dst = '/tmp/candidate.jobs/%s' % os.path.basename(rf)
                dstdir = os.path.dirname(dst)
                if not os.path.isdir(dstdir):
                    os.makedirs(dstdir)
                shutil.copy(rf, dst)

            #import epdb; epdb.st()

#import epdb; epdb.st()
