#!/usr/bin/env python

import json
import logging
import os

from sqlalchemy import create_engine
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import ansibullbot.constants as C


Base = declarative_base()


class Blame(Base):
    __tablename__ = u'blames'
    id = Column(Integer(), primary_key=True)
    file_name = Column(String())
    file_commit = Column(String())
    author_commit = Column(String())
    author_login = Column(String())


class Email(Base):
    __tablename__ = u'email'
    id = Column(Integer())
    login = Column(String())
    email = Column(String(), primary_key=True)


class RateLimit(Base):
    __tablename__ = u'rate_limit'
    id = Column(Integer(), primary_key=True)
    username = Column(String)
    token = Column(String)
    rawjson = Column(String)
    core_rate_limit = Column(Integer)
    core_rate_limit_remaining = Column(Integer)
    query_counter = Column(Integer)


class GithubApiRequest(Base):
    __tablename__ = u'github_api_request'
    id = Column(Integer(), primary_key=True)
    url = Column(String)
    headers = Column(String)
    datafile = Column(String)
    etag = Column(String)
    date = Column(String)
    last_modified = Column(String)
    token = Column(String)


class AnsibullbotDatabase(object):

    '''A sqlite backed database to help with data caching [NOT CONFIG]'''


    # Use this to set the filename and avoid having to deal with migration
    VERSION = '0.2'

    def __init__(self, cachedir='/tmp'):

        self.dbfile = None
        unc = C.DEFAULT_DATABASE_UNC
        if unc.startswith('sqlite:'):
            self.dbfile = unc.replace('sqlite:///', '')
            self.dbfile = os.path.expanduser(self.dbfile)
            self.dbfile = os.path.abspath(self.dbfile)
            dbfiledir = os.path.dirname(self.dbfile)
            if not os.path.exists(dbfiledir):
                os.makedirs(dbfiledir)
            self.dbfile += '_' + self.VERSION
            unc = 'sqlite:///' + self.dbfile

        self.unc = unc

        self.engine = create_engine(self.unc)
        self.session_maker = sessionmaker(bind=self.engine)
        self.session = self.session_maker()

        self.create_tables()

    def delete_db_file(self):
        os.remove(self.dbfile)

    def create_tables(self):

        retries = 0
        while True and retries < 2:
            try:
                Email.metadata.create_all(self.engine)
                Blame.metadata.create_all(self.engine)
                RateLimit.metadata.create_all(self.engine)
                GithubApiRequest.metadata.create_all(self.engine)
                break
            except Exception as e:
                retries += 1
                if self.dbfile and os.path.exists(self.dbfile):
                    self.delete_db_file()

    def get_github_api_request_meta(self, url, token=None):
        if token is None:
            rl = self.session.query(GitubApiRequest).filter(GithubApiRequest.url == url).first()
        else:
            rl = self.session.query(GithubApiRequest).filter(GithubApiRequest.url == url).filter(GithubApiRequest.token == token).first()

        meta = {}
        if rl is not None:
            meta = {
                'url': rl.url,
                'date': rl.date,
                'etag': rl.etag,
                'last_modified': rl.last_modified,
                'datafile': rl.datafile,
                'token': rl.token,
                'headers': json.loads(rl.headers)
            }

        return meta

    def set_github_api_request_meta(self, url, headers, datafile, token=None):
        kwargs = {
            'url': url,
            'date': headers['Date'],
            'etag': headers['ETag'],
            'last_modified': headers['Last-Modified'],
            'datafile': datafile,
            'token': token,
            'headers': json.dumps(dict(headers))
        }

        if token is None:
            current = self.session.query(GitubApiRequest).filter(GithubApiRequest.url == url).first()
        else:
            current = self.session.query(GithubApiRequest).filter(GithubApiRequest.url == url).filter(GithubApiRequest.token == token).first()

        meta = GithubApiRequest(**kwargs)
        self.session.merge(meta)
        try:
            self.session.flush()
            self.session.commit()
        except Exception as e:
            logging.error(e)

    def set_rate_limit(self, username=None, token=None, rawjson=None):

        '''Store the ratelimit json data by user/token'''

        kwargs = {
            'username': username,
            'token': token,
            'core_rate_limit': rawjson['resources']['core']['limit'],
            'core_rate_limit_remaining': rawjson['resources']['core']['remaining'],
            'rawjson': json.dumps(rawjson),
            'query_counter': 0
        }
        rl = RateLimit(**kwargs)
        self.session.merge(rl)
        self.session.flush()
        self.session.commit()

        self.reset_rate_limit_query_counter(username=username, token=token)

    def get_rate_limit_remaining(self, username=None, token=None):

        '''Get the core limit remaining by user/token'''

        rl = None
        rl = self.session.query(RateLimit).filter(RateLimit.token == token).first()
        if rl is None or not hasattr(rl, 'core_rate_limit_remaining'):
            return None
        remaining = rl.core_rate_limit_remaining

        if rl.query_counter is None:
            rl.query_counter = 0
        rl.query_counter += 1
        self.session.merge(rl)
        self.session.flush()
        self.session.commit()

        return remaining

    def get_rate_limit_rawjson(self, username=None, token=None):

        '''Get the ratelimit json by user/token'''

        rl = None
        rl = self.session.query(RateLimit).filter(RateLimit.token == token).first()
        if rl is None or not hasattr(rl, 'core_rate_limit_remaining'):
            return None

        data = None
        try:
            data = rl.rawjson
            data = json.loads(data)
        except Exception as e:
            pass

        # increment the counter to keep track of calls
        if rl.query_counter is None:
            rl.query_counter = 0
        rl.query_counter += 1
        self.session.merge(rl)
        self.session.flush()
        self.session.commit()

        return data

    def get_rate_limit_query_counter(self, username=None, token=None):
        counter = None
        try:
            counter = self.session.query(RateLimit).filter(RateLimit.token == token).first().query_counter
        except Exception as e:
            pass
        return counter

    def reset_rate_limit_query_counter(self, username=None, token=None):
        rl = None
        rl = self.session.query(RateLimit).filter(RateLimit.token == token).first()
        rl.query_counter = 0
        self.session.merge(rl)
        self.session.flush()
        self.session.commit()

    def debug(self):
        import epdb; epdb.st()     
