#!/usr/bin/env python
# Ansible managed. Any local changes will be overwritten.

import cgi
import glob
import os
import sys
import subprocess

def run_command(args):
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (so, se) = p.communicate()
    return (p.returncode, so, se)


def get_process_data():
    # USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
    #[root@centos-1gb-nyc3-01 cgi-bin]# ps aux | fgrep -i triage.py | egrep ^ansibot
    #ansibot   1092 18.2 37.4 600984 380548 pts/2   S+   13:53   3:46
    #   python ./triage.py --debug --verbose --force --skip_no_update --daemonize --daemonize_interval=360
    pdata = {
        'pid': None,
        'cpu': None,
        'mem': None,
        'disk': '0',
    }
    cmd = 'ps aux | fgrep -i triage_ansible.py | egrep ^ansibot'
    (rc, so, se) = run_command(cmd)
    if rc != 0:
        return pdata

    parts = so.split()
    pdata['pid'] = parts[1]
    pdata['cpu'] = parts[2]
    pdata['mem'] = parts[3]

    # disk used
    cmd = "df -h / | tail -n1 | awk '{print $5}'"
    (rc, so, se) = run_command(cmd)
    pdata['disk'] = so.strip()

    return pdata


def _get_log_data():

    LOGDIR='/var/log'
    logfiles = sorted(glob.glob('%s/ansibullbot*' % LOGDIR))
    log_lines = []

    for lf in logfiles:
        if lf.endswith('.log'):
            with open(lf, 'r') as f:
                log_lines = log_lines + f.readlines()

    # trim out and DEBUG lines
    log_info = [x.rstrip() for x in log_lines if ' INFO ' in x]

    # each time the bot starts, it's possibly because of a traceback
    bot_starts = []
    for idx,x in enumerate(log_lines):
        if 'starting bot' in x:
            bot_starts.append(idx)

    # pull out the entire traceback(s) and the relevant issues(s)
    tracebacks = []
    for bs in bot_starts:
        this_issue = None
        this_traceback = []
        if len(log_lines) > 1000:
            lines = log_lines[bs-1000:bs]
        else:
            lines = log_lines[:bs]

        for line in lines:
            if 'DEBUG GET' in line:
                continue
            if 'starting triage' in line:
                this_issue = line.rstrip()
            if 'Traceback (most recent call last)' in line:
                this_traceback.append(line.rstrip())
                continue
            if this_traceback:
                this_traceback.append(line.rstrip())
        if this_traceback:
            tracebacks.append([this_issue] + this_traceback)

    #import epdb; epdb.st()
    return (log_info[-500:], tracebacks)


def get_log_data():

    ratelimit = {
        'total': None,
        'remaining': None,
        'msg': None
    }

    cmd = 'tail -n 1000 "/var/log/ansibullbot.log" | fgrep "x-ratelimit-limit" | tail -n1'
    (rc, so, se) = run_command(cmd)
    if so:
        parts = so.split()

        if "'x-ratelimit-limit':" not in parts:
            #ratelimit['msg'] = '<br>\n'.join(parts)
            pass
        else:
            lidx = parts.index("'x-ratelimit-limit':")
            if lidx:
                ratelimit['total'] = parts[lidx+1].replace("'", '').replace(',', '')
            ridx = parts.index("'x-ratelimit-remaining':")
            if ridx:
                ratelimit['remaining'] = parts[ridx+1].replace("'", '').replace(',', '')

    lines,tracebacks = _get_log_data()

    return (ratelimit, lines, tracebacks)


def get_version_data():
    cmd = 'cd /home/ansibot/ansibullbot; git log --format="%H" -1'

    (rc, so, se) = run_command(cmd)
    if rc == 0 and so:
        commit_hash = so.strip()
        return commit_hash

    return "unknown: %s" % se

pdata = get_process_data()
(ratelimit, loglines, tracebacks) = get_log_data()
version = get_version_data()

rdata = "Content-type: text/html\n"
rdata += "\n"
rdata += "pid: %s<br>\n" % (pdata['pid'] or 'not running')
rdata += "cpu: %s<br>\n" % (pdata['cpu'] or 'not running')
rdata += "mem: %s<br>\n" % (pdata['mem'] or 'not running')
rdata += "disk: %s<br>\n" % (pdata['disk'] or 'N/A')
rdata += "<br>\n"
rdata += "ratelimit total: %s<br>\n" % ratelimit['total']
rdata += "ratelimit remaining: %s<br>\n" % ratelimit['remaining']
rdata += "<br>\n"
rdata += "current version: %s\n" % version
rdata += "<br>\n"
rdata += "################################ INFO LOG ###########################<br>\n"
rdata += '<pre>'
rdata += '\n'.join(loglines[:200])
rdata += "\n"
rdata += '</pre>'
rdata += '<br>'
rdata += "################################ TRACEBACKS #########################<br>\n"
for tb in tracebacks:
    rdata += '<pre>'
    rdata += '\n'.join([x for x in tb if x is not None])
    rdata += '</pre>'
rdata += "<br>\n"

# force error on full disk
if int(pdata['disk'].replace('%', '')) > 98:
    print 'Status: 500 No disk space left'
    print
else:
    print rdata
