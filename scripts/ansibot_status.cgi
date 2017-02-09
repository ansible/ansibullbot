#!/usr/bin/env python

import cgi
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
    }
    cmd = 'ps aux | fgrep -i triage.py | egrep ^ansibot'
    (rc, so, se) = run_command(cmd)
    if rc != 0:
        return None

    parts = so.split()
    pdata['pid'] = parts[1]
    pdata['cpu'] = parts[2]
    pdata['mem'] = parts[3]

    return pdata

def get_log_data():
    cmd = 'tail -n 10 /var/log/ansibullbot.log'
    (rc, so, se) = run_command(cmd)
    lines = []
    for line in so.split('\n'):
        lines.append(line)

    ratelimit = {
        'total': None,
        'remaining': None,
        'msg': None
    }

    cmd = "tail -n 100 /var/log/ansibullbot.log | fgrep 'x-ratelimit-limit' | tail -n1"
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

    return (ratelimit, lines)

pdata = get_process_data()
(ratelimit, loglines) = get_log_data()

rdata = "Content-type: text/html\n"
rdata += "\n"
rdata += "pid: %s<br>\n" % (pdata['pid'] or 'not running')
rdata += "cpu: %s<br>\n" % (pdata['cpu'] or 'not running')
rdata += "mem: %s<br>\n" % (pdata['mem'] or 'not running')
rdata += "<br>\n"
rdata += "ratelimit total: %s<br>\n" % ratelimit['total']
rdata += "ratelimit remaining: %s<br>\n" % ratelimit['remaining']
rdata += "<br>\n"
rdata += '<br>\n'.join(loglines)
rdata += "\n"

print rdata
