#!/opt/anaconda2/bin/python

# $ curl -v -X POST --header "Content-Type: application/json" -d@summaries.json 'http://localhost:5001/summaries?user=ansible&repo=ansible'

import json

from flask import Flask
from flask import jsonify
from flask import request
from flask_pymongo import PyMongo
from pprint import pprint
from werkzeug.exceptions import BadRequest

app = Flask(__name__)
app.config['MONGO_DBNAME'] = 'ansibot_reciever'
mongo = PyMongo(app)
#DB = mongo['github_summaries']
#SUMMARIES = DB['issues']


def get_summary_numbers_for_repo(org, repo):
    pipeline = [
        {'$match': {'github_org': org, 'github_repo': repo}},
        {'$project': {'_id': 0, 'number': 1}}
    ]

    cursor = mongo.db.summaries.aggregate(pipeline)
    res = list(cursor)
    res = [x['number'] for x in res]
    return res


@app.route('/metadata', methods=['GET', 'POST'])
def metadata():
    print('metadata!')
    print(request)
    username = request.args.get('user')
    reponame = request.args.get('repo')
    number = request.args.get('number')
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
            # compare it
            cdict = dict(doc)
            cdict.pop('_id', None)
            if cdict == data:
                res['result'] = 'skipped'
            else:
                mongo.db.metadata.replace_one(doc, data)
                res['result'] = 'replaced'

        return jsonify(res)

    elif request.method == 'GET':
        pass

    return ""


@app.route('/summaries', methods=['GET', 'POST'])
def summaries():
    print('summaries!')
    print(request)

    username = request.args.get('user')
    reponame = request.args.get('repo')
    number = request.args.get('number')
    if number:
        number = int(number)

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
        known = get_summary_numbers_for_repo(username, reponame)
        print('total known: %s' % len(known))

        # group by missing or needs evaluation
        to_insert = []
        to_inspect = []
        for k,v in content.items():

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

            mongo.db.summaries.insert_many(documents)
            res['inserted'] += len(documents)

        # incremental inspect and replace
        if to_inspect:
            for x in to_inspect:
                data = content[x].copy()
                data['github_org'] = username
                data['github_repo'] = reponame
                data['github_number'] = data['number']

                # get the existing document
                doc = mongo.db.summaries.find_one(
                    {'github_org': username, 'github_repo': reponame, 'number': data['number']}
                )
                # compare it
                cdict = dict(doc)
                cdict.pop('_id', None)
                if cdict == data:
                   #print('skip %s' % x)
                    res['skipped'] += 1
                else:
                    #print('replace %s' % x)
                    mongo.db.summaries.replace_one(doc, data)
                    res['replaced'] += 1

        return jsonify(res)


    elif request.method == 'GET':
        print('GET!')

    return 'summaries\n'


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5001)
