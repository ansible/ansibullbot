#!/usr/bin/env python

import ConfigParser
import json
import os
import re
import requests
import subprocess

import ansibullbot.constants as C

from ansibullbot.utils.extractors import extract_template_sections
from ansibullbot.utils.extractors import extract_template_data
from ansibullbot.utils.file_tools import FileIndexer


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
    os.remove(fn)
    return (rc, so, se)


def get_headers():
    headers = {'Authorization': 'token %s' % C.DEFAULT_GITHUB_TOKEN}
    return headers


def run_template_extract(FI, body, number, gtype, sections):
    template_data = extract_template_data(body, number, gtype, sections)
    return template_data


def render_body(ts, section_order):
    body = ''
    for section in section_order:
        section = section.lower()
        if section == 'component name' and ts.get('component_raw'):
            import epdb; epdb.st()

        if section in ts:
            lines = ts[section]
            if lines.startswith(':\n\n'):
                lines = lines.replace(':\n\n', '', 1)
            body += '##### {}\r\n'.format(section.upper())
            body += '\r\n'
            body += lines
            body += '\r\n'
            body += '\r\n'

    #import epdb; epdb.st()
    return body


def sclean(rawtext):
    rawtext = rawtext.lower()
    rawtext = rawtext.replace('\n\n', '')
    rawtext = rawtext.replace('\r\n', '')
    rawtext = rawtext.replace('.', '')
    rawtext = rawtext.replace('`', '')
    rawtext = rawtext.replace(':', '')
    rawtext = rawtext.replace('"', '')
    rawtext = rawtext.replace("'", '')
    return rawtext


def find_component(idata, ts, newbody, comments):
    component = None
    summary = ts.get('summary', newbody)

    for comment in comments:
        # [module: source_control/git.py]
        if '[module: ' in comment['body']:
            m = re.search('.*\[module\:\ ', comment['body'])
            component = comment['body'][m.end():]
            component = component.split(']')[0]
            component = component.split('/')[-1]
            component = component.replace('.py', '')
            component = component + ' module'

    if component is None:
        if sclean(idata['title'].lower().split()[1]) == 'module':
            component = idata['title'].lower().split()[0] + ' module'

        elif sclean(idata['title'].lower().split()[-1]) == 'module':
            component = idata['title'].lower().split()[-2] + ' module'

        elif re.search('.*(using|the|on) (\w+) module.*', sclean(summary)):
            m = re.search('.*(using|the|on) (\w+) module.*', sclean(summary))
            #component = m.group(1) + ' module'
            component = m.groups()[-1] + ' module'

        elif re.search('^(\w+) module.*', sclean(summary)):
            m = re.search('^(\w+) module.*', sclean(summary))
            #component = m.group(1) + ' module'
            component = m.groups()[-1] + ' module'

        elif re.search('.*http://docs.ansible.com/ansible/(\w+)_module.html*', summary):
            # http://docs.ansible.com/ansible/ec2_vpc_module.html#examples
            m = re.search('.*http://docs.ansible.com/ansible/(\w+)_module.html*', summary)
            component = m.group(1) + ' module'

        elif re.search('.*-\ (\w+):', newbody):
            m = re.search('.*-\ (\w+):', newbody)
            if m.groups()[-1] != 'name':
                component = m.groups()[-1] + ' module'

    if component is None and 'Traceback (most recent call last)' in newbody:
        # File "/home/ams/.ansible/tmp/ansible-tmp-1437539129.55-196568771901480/ec2_vpc", line 230
        lines = newbody.split('\n')
        lastline = None
        for line in lines:
            line = line.strip()
            if line.startswith('File "') and 'ansible-tmp' in line:
                lastline = line
        if lastline:
            component = lastline.split('"')[1]
            component = component.split('/')[-1]
            component = component + ' module'

    if component:
        component = sclean(component)

    if component is None:
        print('# title: {}'.format(idata['title']))
        print('what is component for {} ?'.format(idata['html_url']))
        import epdb; epdb.st()

    return component


def get_migrated_issue(body):
    # get migrated issue
    mi = body.split()[-1]
    mi_number = int(mi.split('#')[-1])
    mi_repo = mi.split('#')[0]
    mi_url = 'https://api.github.com/repos/{}/issues/{}'.format(mi_repo, mi_number)
    irr = requests.get(mi_url, headers=get_headers())
    idata = irr.json()
    return idata


def main():
    # need a file indexer to get the template
    FI = FileIndexer(checkoutdir='/tmp/fileindexer')
    FI.update()

    # get the expected sections
    tf_content = FI.get_file_content('.github/ISSUE_TEMPLATE.md')
    tf_sections = extract_template_sections(tf_content, header='#####')
    required_sections = [x.lower() for x in tf_sections.keys() if tf_sections[x]['required']]
    if not required_sections:
        required_sections = ['issue type', 'component name', 'ansible version', 'summary']
    section_order = list(tf_sections.items())
    section_order = sorted(section_order, key=lambda x: x[1]['index'])
    section_order = [x[0] for x in section_order]

    # all known possibilities
    section_names = ['PLUGIN NAME', 'ANSIBLE CONFIGURATION'] + section_order + ['ENVIRONMENT']

    # get the numbers
    script = "#!/bin/bash\n"
    script += "\n"
    script += "URL='https://github.com/ansible/ansible/issues?utf8=%E2%9C%93&q=is%3Aopen%20label%3Aneeds_template%20author%3Aansibot'\n"
    script += "PYTHONPATH=$(pwd) scripts/scrape_github_issues_url $URL\n"
    (rc, so, se) = runscript(script)
    numbers = json.loads(so)
    numbers = sorted(set(numbers))

    for idn,number in enumerate(numbers):
        print('{} {}|{}'.format(number,idn,len(numbers)))
        fixed = []
        iurl = 'https://api.github.com/repos/ansible/ansible/issues/{}'.format(number)
        irr = requests.get(iurl, headers=get_headers())
        idata = irr.json()

        curl = idata['comments_url']
        crr = requests.get(curl, headers=get_headers())
        comments = crr.json()
        if crr.links:
            print('paginated comments')
            nextp = [x for x in crr.links.items() if x[1]['rel'] == 'next'][0][1]['url']
            while nextp:
                nrr = requests.get(nextp, headers=get_headers())
                comments += nrr.json()
                try:
                    nextp = [x for x in nrr.links.items() if x[1]['rel'] == 'next'][0][1]['url']
                except:
                    nextp = None
            #import epdb; epdb.st()

        newbody = idata['body']

        # extract
        ts = run_template_extract(FI, newbody, number, 'issue', section_names)

        # cleanup
        if 'environment' in ts:
            ts['os / environment'] = ts['environment']
            ts.pop('environment', None)

        # what is missing?
        missing = [x for x in required_sections if x.lower() not in ts]
        if not missing:
            print('{} nothing missing'.format(number))
            continue

        # simple sed for this one
        if missing == ['component name'] and 'plugin name' in newbody.lower():
            if 'PLUGIN NAME' in newbody:
                newbody = newbody.replace('PLUGIN NAME', 'COMPONENT NAME')
            if 'Plugin Name' in newbody:
                newbody = newbody.replace('Plugin Name', 'Component Name')
            if 'plugin name' in newbody:
                newbody = newbody.replace('plugin name', 'component name')

            print('{} sed/plugin name/component name'.format(number))
            cr = requests.patch(iurl, headers=get_headers(), data=json.dumps({'body': newbody}))
            if cr.status_code != 200:
                print('failed to edit body {}'.format(idata['html_url']))
                import epdb; epdb.st()
            continue

        if 'summary' in missing:
            ts['summary'] = newbody
            missing.remove('summary')
            fixed.append('summary')

        if 'issue type' in missing:
            # get migrated issue
            try:
                mi = get_migrated_issue(idata['body'])
            except Exception as e:
                print(e)
                mi = None
            if mi:
                itype = None
                # get issue type label from migrated issue
                mi_labels = [x['name'] for x in mi['labels']]
                if 'bug_report' in mi_labels:
                    itype = 'Bug Report'
                elif 'feature_idea' in mi_labels:
                    itype = 'Feature Idea'
                elif 'docs_report' in mi_labels:
                    itype = 'Documentation Report'

                if itype is not None:
                    ts['issue type'] = itype
                    missing.remove('issue type')
                    fixed.append('issue type')

        if 'component name' in missing:
            component = find_component(idata, ts, newbody, comments)
            if component:
                missing.remove('component name')
            ts['component name'] = component
            fixed.append('component name')

        if 'ansible version' in missing:
            labels = [x['name'] for x in idata['labels']]
            labels = [x for x in labels if x.startswith('affects_')]
            labels = sorted(set(labels))
            if labels:
                version = labels[0].replace('affects_', '')
            else:
                version = "N/A"
            missing.remove('ansible version')
            ts['ansible version'] = version
            fixed.append('ansible version')

        if not missing:
            print('# {}'.format(idata['html_url']))
            print('# title: {}'.format(idata['title']))
            print('# component: {}'.format(ts['component name']))
            print('# version: {}'.format(ts['ansible version']))
            print('# fixed: {}'.format(fixed))

            newbody = render_body(ts, section_order)
            print('<====================================================>')
            print(newbody)
            print('<====================================================>')
            import epdb; epdb.st()

            cr = requests.patch(iurl, headers=get_headers(), data=json.dumps({'body': newbody}))
            if cr.status_code != 200:
                print('failed to edit body {}'.format(idata['html_url']))
                import epdb; epdb.st()
            continue


        print('no solution(s) for {} {}'.format(idata['html_url'], missing))

    print('DONE')


if __name__ == "__main__":
    main()
