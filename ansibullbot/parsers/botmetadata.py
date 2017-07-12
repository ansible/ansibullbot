#!/usr/bin/env python

import yaml
from string import Template

import ruamel
from ruamel.yaml import YAML as rYAML

class BotMetadataParser(object):

    @staticmethod
    def parse_yaml(data):

        def clean_list_items(inlist):
            if isinstance(inlist, list):
                inlist = str(inlist)
            if '&' in inlist:
                import epdb; epdb.st()
            inlist = inlist.replace("[", '')
            inlist = inlist.replace("]", '')
            inlist = inlist.replace("'", '')
            inlist = inlist.replace(",", '')
            inlist = inlist.split()
            return inlist

        def fix_lists(data):
            for k,v in data['files'].items():
                if v is None:
                    continue

                for k2,v2 in v.items():
                    if isinstance(v2, str) and '$' in v2:
                        tmpl = Template(v2)
                        newv2 = tmpl.substitute(**data['macros'])
                        newv2 = clean_list_items(newv2)
                        data['files'][k][k2] = newv2
                        v2 = newv2
                    if isinstance(v2, (str, unicode)):
                        data['files'][k][k2] = v2.split()

            return data

        def fix_keys(data):
            replace = []
            for k in data['files'].keys():
                if '$' in k:
                    replace.append(k)
            for x in replace:
                tmpl = Template(x)
                newkey = tmpl.substitute(**data['macros'])
                data['files'][newkey] = data['files'][x]
                data['files'].pop(x, None)

            return data

        def extend_labels(data):
            for k,v in data['files'].items():
                # labels from path(s)
                if v is None:
                    continue
                labels = v.get('labels', [])
                if isinstance(labels, str):
                    labels = labels.split()
                    labels = [x.strip() for x in labels if x.strip()]
                path_labels = [x.strip() for x in k.split('/') if x.strip()]
                for x in path_labels:
                    x = x.replace('.py', '')
                    x = x.replace('.ps1', '')
                    if x not in labels:
                        labels.append(x)
                data['files'][k]['labels'] = sorted(set(labels))

            return data

        def fix_teams(data):
            for k,v in data['macros'].items():
                if v is None:
                    continue
                if not k.startswith('team_') or isinstance(v, list):
                    continue
                names = v.split()
                data['macros'][k] = names
            return data

        #################################
        #   PARSE
        #################################

        ydata = yaml.load(data)

        # fix the team macros
        ydata = fix_teams(ydata)

        # fix the macro'ized file keys
        ydata = fix_keys(ydata)

        # convert string vals to a maintainers key in a dict
        for k,v in ydata['files'].items():
            if isinstance(v, (str, unicode)):
                ydata['files'][k] = {
                    'maintainers': v
                }

        # replace macros in files section
        ydata = fix_lists(ydata)

        # extend labels by filepath
        ydata = extend_labels(ydata)

        return ydata
