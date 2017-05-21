'''

    whooshalchemy flask extension
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Adds whoosh indexing capabilities to SQLAlchemy models for Flask
    applications.

    :copyright: (c) 2012 by Karl Gyllstrom
    :license: BSD (see LICENSE.txt)

'''



from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_testing import TestCase
import flask_whooshalchemy as wa
from whoosh.analysis import StemmingAnalyzer, DoubleMetaphoneFilter

import datetime
import os
import tempfile
import shutil


db = SQLAlchemy()


class BlogishBlob(object):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text)
    content = db.Column(db.String)
    blurb = db.Column(db.Unicode)
    ignored = db.Column(db.Unicode)
    created = db.Column(db.DateTime(), default=datetime.datetime.utcnow())

    def __repr__(self):
        return '{0}(title={1})'.format(self.__class__.__name__, self.title)


def _after_flush(app, changes):
    from sqlalchemy.orm import EXT_CONTINUE
    return EXT_CONTINUE


class ObjectA(db.Model, BlogishBlob):
    __tablename__ = 'objectA'
    __searchable__ = ['title', 'content', 'blurb']


class ObjectB(db.Model, BlogishBlob):
    __tablename__ = 'objectB'
    __searchable__ = ['title', 'content', 'content']  # dup intentional


class ObjectC(db.Model, BlogishBlob):
    __tablename__ = 'objectC'
    __searchable__ = ['title', 'field_that_doesnt_exist']
    
class ObjectD(db.Model, BlogishBlob):
    __tablename__ = 'objectD'
    __searchable__ = ['title']
    __analyzer__ = StemmingAnalyzer() | DoubleMetaphoneFilter()


class Tests(TestCase):
    DATABASE_URL = 'sqlite://'
    TESTING = True

    def create_app(self):
        tmp_dir = tempfile.mkdtemp()

        app = Flask(__name__)

        app.config['WHOOSH_BASE'] = os.path.join(tmp_dir, 'whoosh')

        return app

    def setUp(self):
        db.init_app(self.app)
        db.create_all()

    def tearDown(self):
        try:
            shutil.rmtree(self.app.config['WHOOSH_BASE'])
        except OSError as e:
            if e.errno != 2:  # code 2 - no such file or directory
                raise

        db.drop_all()

    def test_all(self):
        title1 = 'a slightly long title'
        title2 = 'another title'
        title3 = 'wow another title'

        obj = ObjectA(title='title', blurb='this is a blurb')
        db.session.add(obj)
        db.session.commit()

        self.assertEqual(len(list(ObjectA.query.whoosh_search('blurb'))), 1)
        db.session.delete(obj)
        db.session.commit()

        db.session.add(ObjectA(title=title1, content='hello world', ignored='no match'))
        db.session.commit()

        self.assertEqual(len(list(ObjectA.query.whoosh_search('what'))), 0)
        self.assertEqual(len(list(ObjectA.query.whoosh_search('no match'))), 0)
        self.assertEqual(len(list(ObjectA.query.whoosh_search('title'))), 1)
        self.assertEqual(len(list(ObjectA.query.whoosh_search('hello'))), 1)

        db.session.add(ObjectB(title='my title', content='hello world'))
        db.session.commit()

        # make sure does not interfere with ObjectA's results
        self.assertEqual(len(list(ObjectA.query.whoosh_search('what'))), 0)
        self.assertEqual(len(list(ObjectA.query.whoosh_search('title'))), 1)
        self.assertEqual(len(list(ObjectA.query.whoosh_search('hello'))), 1)

        self.assertEqual(len(list(ObjectB.query.whoosh_search('what'))), 0)
        self.assertEqual(len(list(ObjectB.query.whoosh_search('title'))), 1)
        self.assertEqual(len(list(ObjectB.query.whoosh_search('hello'))), 1)

        obj2 = ObjectA(title=title2, content='a different message')
        db.session.add(obj2)
        db.session.commit()

        self.assertEqual(len(list(ObjectA.query.whoosh_search('what'))), 0)
        l = list(ObjectA.query.whoosh_search('title'))
        self.assertEqual(len(l), 2)

        # ranking should always be as follows, since title2 should have a higher relevance score

        self.assertEqual(l[0].title, title2)
        self.assertEqual(l[1].title, title1)

        self.assertEqual(len(list(ObjectA.query.whoosh_search('hello'))), 1)
        self.assertEqual(len(list(ObjectA.query.whoosh_search('message'))), 1)

        self.assertEqual(len(list(ObjectB.query.whoosh_search('what'))), 0)
        self.assertEqual(len(list(ObjectB.query.whoosh_search('title'))), 1)
        self.assertEqual(len(list(ObjectB.query.whoosh_search('hello'))), 1)
        self.assertEqual(len(list(ObjectB.query.whoosh_search('message'))), 0)

        db.session.add(ObjectA(title=title3, content='a different message'))
        db.session.commit()

        l = list(ObjectA.query.whoosh_search('title'))
        self.assertEqual(len(l), 3)
        self.assertEqual(l[0].title, title2)
        self.assertEqual(l[1].title, title3)
        self.assertEqual(l[2].title, title1)

        db.session.delete(obj2)
        db.session.commit()

        l = list(ObjectA.query.whoosh_search('title'))
        self.assertEqual(len(l), 2)
        self.assertEqual(l[0].title, title3)
        self.assertEqual(l[1].title, title1)

        two_days_ago = datetime.date.today() - datetime.timedelta(2)

        title4 = 'a title that is significantly longer than the others'

        db.session.add(ObjectA(title=title4, created=two_days_ago))
        db.session.commit()

        one_day_ago = datetime.date.today() - datetime.timedelta(1)

        recent = list(ObjectA.query.whoosh_search('title')
                .filter(ObjectA.created >= one_day_ago))

        self.assertEqual(len(recent), 2)
        self.assertEqual(l[0].title, title3)
        self.assertEqual(l[1].title, title1)

        three_days_ago = datetime.date.today() - datetime.timedelta(3)

        l = list(ObjectA.query.whoosh_search('title')
                .filter(ObjectA.created >= three_days_ago))

        self.assertEqual(len(l), 3)
        self.assertEqual(l[0].title, title3)
        self.assertEqual(l[1].title, title1)
        self.assertEqual(l[2].title, title4)

        title5 = 'title with title as frequent title word'

        db.session.add(ObjectA(title=title5))
        db.session.commit()

        l = list(ObjectA.query.whoosh_search('title'))
        self.assertEqual(len(l), 4)
        self.assertEqual(l[0].title, title5)
        self.assertEqual(l[1].title, title3)
        self.assertEqual(l[2].title, title1)
        self.assertEqual(l[3].title, title4)

        # test limit
        l = list(ObjectA.query.whoosh_search('title', limit=2))
        self.assertEqual(len(l), 2)
        self.assertEqual(l[0].title, title5)
        self.assertEqual(l[1].title, title3)

        # XXX should replace this with a new function, but I can't figure out
        # how to do this cleanly with flask sqlalchemy and testing

        db.drop_all()
        db.create_all()

        title1 = 'my title'
        db.session.add(ObjectA(title=title1, content='hello world'))
        db.session.commit()

        l = list(ObjectA.query.whoosh_search('title'))
        self.assertEqual(len(l), 1)

        l = list(ObjectA.query.whoosh_search('hello'))
        self.assertEqual(len(l), 1)

        l = list(ObjectA.query.whoosh_search('title', fields=('title',)))
        self.assertEqual(len(l), 1)
        l = list(ObjectA.query.whoosh_search('hello', fields=('title',)))
        self.assertEqual(len(l), 0)

        l = list(ObjectA.query.whoosh_search('title', fields=('content',)))
        self.assertEqual(len(l), 0)
        l = list(ObjectA.query.whoosh_search('hello', fields=('content',)))
        self.assertEqual(len(l), 1)

        l = list(ObjectA.query.whoosh_search('hello dude', fields=('content',), or_=True))
        self.assertEqual(len(l), 1)

        l = list(ObjectA.query.whoosh_search('hello dude', fields=('content',), or_=False))
        self.assertEqual(len(l), 0)

        # new function: test chaining
        db.drop_all()
        db.create_all()

        db.session.add(ObjectA(title='title one', content='a poem'))
        db.session.add(ObjectA(title='title two', content='about testing'))
        db.session.add(ObjectA(title='title three', content='is delightfully tested'))
        db.session.add(ObjectA(title='four', content='tests'))
        db.session.commit()

        self.assertEqual(len(list(ObjectA.query.whoosh_search('title'))), 3)
        self.assertEqual(len(list(ObjectA.query.whoosh_search('test'))), 3)

        # chained query, operates as AND
        self.assertEqual(len(list(ObjectA.query.whoosh_search('title').whoosh_search('test'))),
                2)


    def test_invalid_attribute(self):
        db.session.add(ObjectC(title='my title', content='hello world'))
        self.assertRaises(AttributeError, db.session.commit)

    def test_default_analyzer(self):
        db.session.add(ObjectA(title='jumping', content=''))
        db.session.commit()
        assert ['jumping'] == [obj.title for obj in ObjectA.query.whoosh_search('jump')]

    def test_custom_analyzer(self):
        from whoosh.analysis import SimpleAnalyzer
        self.app.config['WHOOSH_ANALYZER'] = SimpleAnalyzer()
        db.init_app(self.app)
        db.create_all()
        db.session.add(ObjectA(title='jumping', content=''))
        db.session.commit()
        assert not list(ObjectA.query.whoosh_search('jump'))
        assert ['jumping'] == [obj.title for obj in ObjectA.query.whoosh_search('jumping')]

        db.session.add(ObjectD(title='Travelling', content='Stemming'))
        db.session.add(ObjectD(title='travel', content='Unstemmed and normal'))
        db.session.add(ObjectD(title='trevel', content='Mispelt'))
        
        db.session.commit()
        # When mispelt on either the indexed side or the query side, they should all return 3 due to the DoubleMetaphoneFilter
        self.assertEqual(len(list(ObjectD.query.whoosh_search('travelling'))), 3)
        self.assertEquals(len(list(ObjectD.query.whoosh_search('trovel'))), 3)


if __name__ == '__main__':
    import unittest
    unittest.main()
