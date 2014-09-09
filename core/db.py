from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, scoped_session
from time import time, mktime
import hashlib
import feedparser

Base = declarative_base()

SKIPPED = "SKIPPED"
RECIEVED = "RECIEVED"
SCHEDULED = "SCHEDULED"
FORMATTED = "FORMATTED"
DROPPED = "DROPPED"
WAIT = "WAIT"
SENT = "SENT"

class Atom(Base):
    """ Atom Log
    ID                < The application ID for ref
    FEED_ID           < The application ID for the Atom List
    UNIQ_ID           < The unique field to identify the atom
    RECV_DTS          < The unix timestamp the atom was recieved
    SCHED_DTS         < The scheduled unix timestamp for the atom to be tweeted
    BITLY             < The bitly associated with this atom.
    STATUS (RECIEVED, SCHEDULING, FORMATING, WAIT, DROPPED) < The status of this atom as it goes though the queus
    """

    __tablename__ = "Atom"
    id = Column(Integer, primary_key=True)
    feed_id = Column(Integer, ForeignKey('RssFeed.id'))
    uniq_id = Column(String(255), nullable=False, unique=True)
    recv_dts = Column(Integer)
    publish_dts = Column(Integer)
    sched_dts = Column(Integer)
    bitly = Column(String(255))
    status = Column(String(255))

    def __init__(self, **kwargs):
        self.feed_id = kwargs.get('feed_id', None)
        self.uniq_id = kwargs.get('uniq_id', None)
        self.recv_dts = kwargs.get('recv_dts', None)
        self.publish_dts = kwargs.get('publish_dts', None)
        self.sched_dts = kwargs.get('sched_dts', None)
        self.bitly = kwargs.get('bitly', None)
        self.status = kwargs.get('status', None)

    @staticmethod
    def set_state(status, uid, session):
        atom = session.query(Atom).filter(Atom.uniq_id == uid).first()
        if atom: atom.status = status

    @staticmethod
    def set_bitly(short_link, uid, session):
        atom = session.query(Atom).filter(Atom.uniq_id == uid).first()
        if atom: atom.bitly = short_link
    
    def __repr__(self):
        return "<Atom id({0}), feed({1}), uniq({2}), recv({3}), sched({4}), status({5})>".format(
            self.id, 
            self.feed.name,
            self.uniq_id, 
            self.recv_dts, 
            self.sched_dts,
            self.status,
        )


class RssFeed(Base):
    """ Atom List
    ID                < Application ID to ref
    NAME              < The application name of the feed
    URL               < The URL to the RSS Feed
    ORDER             < The order to scan for new atoms in each cycle.
    ENABLED           < If the feed is enaled
    """

    __tablename__ = "RssFeed"
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    hashtags = Column(String(255))
    url = Column(String(255), unique=True)
    order = Column(Integer)
    enable = Column(Boolean)
    atoms = relationship("Atom", backref="feed")

    def __init__(self, **kwargs):
        self.id = kwargs.get('id', None)
        self.name = kwargs.get('name', None)
        self.hashtags = kwargs.get('hashtags', None)
        self.url = kwargs.get('url', None)
        self.order = kwargs.get('order', None)
        self.enable = kwargs.get('enable', None)

    @staticmethod
    def new(url, hashtags=None, order=500, enable=True):
        feed = feedparser.parse(url)
        if not feed: return None

        _htags = " ".join(hashtags) if hashtags else ""
        print("With tags:",_htags)

        return RssFeed(
            name = feed['channel']['title'].encode("ascii", errors='ignore'),
            hashtags=_htags,
            url = url,
            order = order,
            enable = enable,
        )

    def get_new_atoms(self, status="RECIEVED"):
        """ Query the feed and find new atoms.
        
        New atoms will automaticly be added to the database with the provided status (default: "RECIEVED")
        
        Arguments:
            status - Optional: The staus to set the new records to
        """
        required_keys = ['title', 'published_parsed', 'link', 'title_detail', 'tags']

        feed = feedparser.parse(self.url)
        for atom in feed['items']:

            if all(req_key in atom for req_key in required_keys) and atom['title_detail']['type'] == 'text/plain':
                link = atom['link']
                ident = hashlib.md5(link).hexdigest()
                recv = int(time())

                ## Make sure it's new
                if ident in [a.uniq_id for a in self.atoms]: continue

                ## update the tags
                #tags = set(["#"+tag['term'].encode("ascii", errors="ignore").title().replace(' ', '') for tag in atom['tags']])
                tags = set()
                for _t in self.hashtags.split(' '):
                    tags.add(_t.encode("ascii", errors="ignore"))

                ## Add to child
                self.atoms.append(Atom(
                    uniq_id=ident,
                    recv_dts=recv,
                    publish_dts=int(mktime(atom['published_parsed'])),
                    status=status
                ))

                yield {
                    'title':atom['title_detail']['value'].encode("ascii", errors="ignore"),
                    'body':atom.get('summary', None),
                    'link':link,
                    'tags':tags,
                    'ident':ident,
                    'recv':recv,
                }

    def __repr__(self):
        return "<RssFeed id({0}), name({1}), order({2}), enable({3})>".format(
            self.id,
            self.name,
            self.order,
            self.enable,
        )


class Joke(Base):
    """ Joke
    ID                < The application ID to ref
    BODY              < The pre-formatted body of the joke
    SENT              < Flag if this joke has been used or not
    """

    __tablename__ = "Joke"
    id = Column(Integer, primary_key=True)
    body = Column(String(160))
    sent = Column(Boolean)

    def __init__(self, **kwargs):
        self.id = kwargs.get('id', None)
        self.body = kwargs.get('body', None)
        self.sent = kwargs.get('sent', False)

    @staticmethod
    def new(body):
        if len(body) > 140:
            raise Exception("Joke is to large")
        return Joke( body=body )

    @staticmethod
    def get_next(session):
        joke = session.query(Joke).filter(Joke.sent == False).first()
        if not joke: return None
        joke.sent = True
        return joke
        

    def __repr__(self):
        return "<Joke id({0}), sent({1})>".format(
            self.id,
            self.sent,
        )


class Tweet(Base):
    """ Tweet
    ID                < The application ID for ref
    TYPE (JOKE, ATOM) < The source table for this tweet. ie: joke or atom
    SOURCE_ID         < The application ID of the record in the joke or atom table.
    BODY              < The actual body that was tweeted
    SENT_DTS          < The unix timestamp the tweet was sent.
    """

    __tablename__ = "Tweet"
    id = Column(Integer, primary_key=True)
    type = Column(String(10))
    source_id = Column(Integer)
    body = Column(String(140))
    sent_dts = Column(Integer)

    def __init__(self, **kwargs):
        self.id = kwargs.get('id', None)
        self.type = kwargs.get('type', None)
        self.source_id = kwargs.get('source_id', None)
        self.body = kwargs.get('body', None)
        self.sent_dts = kwargs.get('sent_dts', None)

    def __repr__(self):
        return "<Tweet id({0}), type({1}), source_id({2}), sent_dts({3})>".format(
            self.id,
            self.type,
            self.source_id,
            self.sent_dts,
        )


def Session(dbschema):
    """ Create a session """
    engine = create_engine(dbschema)
    return scoped_session(sessionmaker(bind=engine))


def install(dbschema):
    """ Create the database """
    engine = create_engine(dbschema)
    Base.metadata.create_all(engine)

