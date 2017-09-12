#!/usr/bin/env python

import ConfigParser
import json
import os
import requests
import subprocess

import ansibullbot.constants as C


def run_command(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (so, se) = p.communicate()
    return (p.returncode, so, se)

def runscript(script):
    fn = 'tmpscript.sh'
    with open(fn, 'wb') as f:
        f.write(script)
    (rc, so, se) = run_command('chmod +x {}'.format(fn))
    (rc, so, se) = run_command('./{}'.format(fn))
    #os.remove(fn)
    return (rc, so, se)

def get_headers():
    headers = {'Authorization': 'token %s' % C.DEFAULT_GITHUB_TOKEN}
    return headers

def main():

    script = "#!/bin/bash\n"
    script += "\n"
    script += "URL='https://github.com/ansible/ansible/issues?utf8=%E2%9C%93&q=is%3Aissue%20is%3Aopen%20biomassives'\n"
    script += "PYTHONPATH=$(pwd) scripts/scrape_github_issues_url $URL\n"

    (rc, so, se) = runscript(script)
    numbers = json.loads(so)
    numbers = sorted(set(numbers))

    for number in numbers:
        print(number)
        iurl = 'https://api.github.com/repos/ansible/ansible/issues/{}'.format(number)
        irr = requests.get(iurl, headers=get_headers())
        idata = irr.json()
        curl = idata['comments_url']
        crr = requests.get(curl, headers=get_headers())
        comments = crr.json()
        if crr.links:
            import epdb; epdb.st()

        for comment in comments:
            if comment['user']['login'] == 'biomassives':
                drr = requests.delete(comment['url'], headers=get_headers())
                if drr.status_code != 204:
                    import epdb; epdb.st()

        print('done with {}'.format(number))

    print('DONE')


if __name__ == "__main__":
    main()
