#!/usr/bin/env python

# $ curl -v -X POST --header "Content-Type: application/json" -d@summaries.json 'http://localhost:5001/summaries?user=ansible&repo=ansible'

import datetime
import glob
import gzip
import json

import pymongo

from bson.json_util import dumps
from flask import Flask
from flask import jsonify
from flask import request
from flask_pymongo import PyMongo
from werkzeug.exceptions import BadRequest

app = Flask(__name__)
app.config['MONGO_DBNAME'] = 'ansibot_reciever'
app.config['MONGO_URI'] = 'mongodb://localhost:27017/ansibot_reciever'
mongo = PyMongo(app)


def get_summary_numbers_for_repo(org, repo, collection_name=None):
    pipeline = [
        {'$match': {'github_org': org, 'github_repo': repo}},
        {'$project': {'_id': 0, 'number': 1}}
    ]

    if collection_name:
        collection = getattr(mongo.db, collection_name)
        cursor = collection.aggregate(pipeline)
    else:
        cursor = mongo.db.summaries.aggregate(pipeline)

    res = list(cursor)
    res = [x['number'] for x in res]
    return res


def get_summary_numbers_with_state_for_repo(org, repo, collection_name=None):
    pipeline = [
        {'$match': {'github_org': org, 'github_repo': repo}},
        {'$project': {'_id': 0, 'state': 1, 'number': 1}}
    ]

    if collection_name:
        collection = getattr(mongo.db, collection_name)
        cursor = collection.aggregate(pipeline)
    else:
        cursor = mongo.db.summaries.aggregate(pipeline)

    res = list(cursor)
    return res


@app.route('/actions', methods=['POST'])
def store_action():
    username = request.args.get('user')
    reponame = request.args.get('repo')
    number = request.args.get('number')

    if not username or not reponame or not number:
        raise BadRequest('user and repo and number must be supplied as parameters')

    content = request.get_json()
    data = content.copy()
    data['github_org'] = username
    data['github_repo'] = reponame
    data['github_number'] = int(number)
    data['datetime'] = datetime.datetime.utcnow()

    mongo.db.actions.insert_one(data)

    return jsonify({'result': 'ok'})


@app.route('/actions', methods=['GET'])
def list_actions():
    username = request.args.get('user')
    reponame = request.args.get('repo')

    if not username or not reponame:
        raise BadRequest('user and repo must be supplied as parameters')

    query = {'github_org': username, 'github_repo': reponame}

    number = request.args.get('number')
    if number:
        query['github_number'] = int(number)

    start = request.args.get('start')
    end = request.args.get('end')
    if start or end:
        query['datetime'] = {}
    if start:
        query['datetime']['$gte'] = datetime.datetime.fromisoformat(start)
    if end:
        query['datetime']['$lte'] = datetime.datetime.fromisoformat(end)

    res = mongo.db.actions.find(query).sort("_id", pymongo.DESCENDING)

    return dumps(res)


@app.route('/dedupe', methods=['GET'])
def dedupe_summaries():
    # summaries
    cursor = mongo.db.summaries.find()
    results = list(cursor)
    summaries = {}
    for res in results:
        gn = res.get('github_number') or res.get('number')
        key = '%s-%s-%s' % (res['github_org'], res['github_repo'], gn)
        if key not in summaries:
            summaries[key] = res
        else:
            mongo.db.summaries.remove(res)

    # metadata
    cursor = mongo.db.metadata.find()
    results = list(cursor)
    metadata = {}
    for res in results:
        gn = res.get('github_number') or res.get('number')
        key = '%s-%s-%s' % (res['github_org'], res['github_repo'], gn)
        if key not in metadata:
            metadata[key] = res
        else:
            mongo.db.metadata.remove(res)

    return jsonify({'result': 'ok'})


@app.route('/metadata', methods=['GET', 'POST'])
def metadata():
    print('metadata!')
    print(request)
    username = request.args.get('user')
    reponame = request.args.get('repo')
    number = request.args.get('number')
    keys = request.args.getlist('key')
    if number:
        number = int(number)

    if not username or not reponame or not number:
        raise BadRequest('user and repo and number must be supplied as parameters')

    if request.method == 'POST':

        res = {'result': None}

        content = request.get_json()
        data = content.copy()
        data['github_org'] = username
        data['github_repo'] = reponame
        data['github_number'] = number
        data['number'] = number

        # get the existing document
        doc = mongo.db.metadata.find_one(
            {'github_org': username, 'github_repo': reponame, 'github_number': number}
        )

        if not doc:
            mongo.db.metadata.insert_one(data)
            res['result'] = 'inserted'
        else:
            mongo.db.metadata.replace_one({'html_url': data['html_url']}, data)
            res['result'] = 'replaced'

        return jsonify(res)

    elif request.method == 'GET':

        if not keys:
            # get the existing document
            cursor = mongo.db.metadata.find(
                {'github_org': username, 'github_repo': reponame, 'github_number': number}
            )
        else:
            pipeline = [
                {'$match': {'github_org': username, 'github_repo': reponame, 'github_number': number}},
            ]
            project = {'_id': 0, 'number': 1}
            for keyname in keys:
                project[keyname] = 1
            pipeline.append({'$project': project})
            cursor = mongo.db.metadata.aggregate(pipeline)

        docs = list(cursor)
        docs = [dict(x) for x in docs]
        for idx, x in enumerate(docs):
            x.pop('_id', None)
            docs[idx] = x
        return jsonify(docs)

    return ""


@app.route('/summaries', methods=['GET', 'POST'])
@app.route('/html_summaries', methods=['GET', 'POST'])
def summaries():

    rule = request.url_rule
    if rule.rule.endswith('html_summaries'):
        collection_name = 'html_summaries'
    else:
        collection_name = 'summaries'

    print('{}!'.format(collection_name))
    print(request)

    username = request.args.get('user')
    reponame = request.args.get('repo')
    state = request.args.get('state')
    number = request.args.get('number')
    if number:
        number = int(number)
    print(request.args)
    print(username)
    print(reponame)
    print(number)

    if not username or not reponame:
        raise BadRequest('user and repo must be supplied as parameters')

    if request.method == 'POST':
        content = request.get_json()
        res = {
            'inserted': 0,
            'replaced': 0,
            'skipped': 0
        }

        # make list of known numbers for namespace/repo
        known = get_summary_numbers_for_repo(username, reponame, collection_name=collection_name)
        print('total known: %s' % len(known))

        # group by missing or needs evaluation
        to_insert = []
        to_inspect = []
        for k, v in content.items():

            if v['number'] not in known:
                to_insert.append(k)
            else:
                to_inspect.append(k)

        # uniqify
        to_insert = sorted(set(to_insert))
        to_inspect = sorted(set(to_inspect))

        # bulk insert
        if to_insert:
            documents = []
            for x in to_insert:
                data = content[x].copy()
                data['github_org'] = username
                data['github_repo'] = reponame
                data['github_number'] = data['number']
                documents.append(data)

            print('insert {} summaries'.format(len(documents)))
            mongo.db.summaries.insert_many(documents)
            res['inserted'] += len(documents)

        # incremental inspect and replace
        if to_inspect:

            known_list = get_summary_numbers_with_state_for_repo(username, reponame, collection_name=collection_name)
            known_states = {}
            for x in known_list:
                known_states[str(x['number'])] = x['state']

            print('inspecting {} summaries'.format(len(to_inspect)))
            for x in to_inspect:
                data = content[x].copy()
                data['github_org'] = username
                data['github_repo'] = reponame
                data['github_number'] = data['number']


                if data['state'] != known_states[str(data['number'])]:
                    print('replacing {}'.format(data['number']))
                    filterdict = {'github_org': username, 'github_repo': reponame, 'github_number': data['number']}
                    collection = getattr(mongo.db, collection_name)
                    collection.replace_one(filterdict, data)

        return jsonify(res)

    elif request.method == 'GET':
        # get the existing document
        qdict = {'github_org': username, 'github_repo': reponame}
        if number:
            qdict['number'] = number
        if state:
            qdict['state'] = state
        collection = getattr(mongo.db, collection_name)
        cursor = collection.find(qdict)
        docs = list(cursor)
        docs = [dict(x) for x in docs]
        for idx, x in enumerate(docs):
            x.pop('_id', None)
            docs[idx] = x
        print(len(docs))
        return jsonify(docs)

    return 'summaries\n'


#####################################################
#   LOGGING PAGE
#####################################################

def strip_line_json(line):
    # 2018-06-07 15:52:51,831 DEBUG GET https://api.github.com/repos/ansible/ansible/issues/28061/events {'Authorization'
    # null ==> 200 {DATA}

    parts = line.split()

    data = {
        'date': parts[0],
        'time': parts[1],
        'loglevel': parts[2],
        'action': parts[3],
        'url': parts[4],
    }

    for k, v in data.items():
        line = line.replace(v, '', 1)
    line = line.lstrip()

    header_index = line.index('}') + 1
    header = line[:header_index]
    line = line.replace(header, '', 1)
    header = eval(header)
    data['request_header'] = header

    jdata_index = line.index('{')
    jdata = line[jdata_index:]
    header2 = jdata[:jdata.index('}')+1]
    line = line.replace(header2, '', 1)
    line = line.lstrip()
    header2 = eval(header2)
    data['response_header'] = header2

    dict_index = line.index('{')
    list_index = line.index('[')
    if dict_index < list_index:
        jdata = line[dict_index:]
    else:
        jdata = line[list_index:]

    data['data'] = json.loads(jdata)

    return data


@app.route('/logs', methods=['GET', 'POST'])
@app.route('/logs/<path:issue>', methods=['GET', 'POST'])
def logs(issue=None):
    LOGDIR = '/var/log'
    logfiles = sorted(glob.glob('%s/ansibullbot*' % LOGDIR))
    log_lines = []

    for lf in logfiles:
        if lf.endswith('.log'):
            with open(lf, 'r') as f:
                log_lines = log_lines + f.readlines()
        # consume the compressed logs too if looking for a specific issue
        elif issue and lf.endswith('.gz'):
            with gzip.open(lf, 'rb') as zf:
                file_data = zf.readlines()
            log_lines.extend(file_data)

    # if the caller doesn't want a specific issue, get the tail of the log and all tracebacks
    if not issue:
        # trim out and DEBUG lines
        log_info = [x.rstrip() for x in log_lines if ' INFO ' in x]

        # each time the bot starts, it's possibly because of a traceback
        bot_starts = []
        for idx, x in enumerate(log_lines):
            if 'starting bot' in x:
                bot_starts.append(idx)

        tracebacks = []
        for bs in bot_starts:
            this_issue = None
            this_traceback = None
            for idx, x in enumerate(log_lines):
                if 'starting triage' in x:
                    this_issue = x
                    continue
                if this_issue and x.endswith('Traceback (most recent call last):'):
                    this_traceback = [x]
                    continue
                if this_traceback:
                    this_traceback.append(x)
                if idx == bs:
                    break

            # only keep things that were actually tracebacks
            if this_traceback is not None:
                if 'Exception' in this_traceback[-2]:
                    tracebacks.append((this_issue, this_traceback))

        return jsonify((log_info[-100:], tracebacks))

    # filter out lines relevant to the issue
    number = issue.split('/')[-1]
    issue_log = []
    inphase = False
    for ll in log_lines:
        ll = ll.rstrip()
        if not inphase and 'starting triage' in ll and ll.endswith('/' + number):
            inphase = True
            issue_log.append(ll)
            continue
        if inphase and 'finished triage' in ll and ll.endswith('/' + number):
            inphase = False
            continue

        if inphase:
            issue_log.append(ll)

    # grep out each time the issue was triaged
    sessions = [x for x in issue_log if 'starting triage' in x]

    # assemble the datastructure for return
    issue_data = {
        'number': number,
        'triage_count': len(sessions),
        'triage_times': [' '.join(x.split()[0:2]) for x in sessions],
        'log': issue_log,
        'api': {}
    }

    # parse out any api data requested for this issue
    for ll in issue_log:
        if 'DEBUG GET' in ll:
            data = strip_line_json(ll)
            issue_data['api'][data['url']] = data

    return jsonify(issue_data)


if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=5001)
