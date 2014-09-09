#!/usr/bin/env python2

from threading import Thread, Event
from argparse import ArgumentParser, REMAINDER
from core import Config, db, utils
from sys import argv
import re

def arg_install_db(args, params):
    ap = ArgumentParser(description="Install the TwitterBot database", usage="%(prog)s gendb [options]")
    ap.add_argument("schema", help="The sqlalchemy dbschema used to create the database")
    _args = ap.parse_args(args)
    
    print("Installing database: {0}".format(_args.schema))
    db.install(_args.schema)
    print("Success!")


def arg_genrc(args, params):
    ap = ArgumentParser(description="Create a new run control file for TwitterBot", usage="%(prog)s genrc [options]")
    ap.add_argument("path", help="The path to save the new run control file")
    _args = ap.parse_args(args)
    
    print("This wizard will help you setup a config file.")
    print("Please answer the following questions.")

    conf = Config(_args.path)
    cp, _iter = conf.create()

    for c in _iter():
        section = c.getSection()
        print("\nConfiguration for section: {0}".format(section))
        for key, fn_fmt in c.getParams():
            print("\n{0}".format(fn_fmt.__doc__))
            while 1:
                value = raw_input("{0}: ".format(key))

                ## Verify input was given
                if len(value) == 0: 
                    print("Please provide a value.")
                    continue

                ## Validate input using the format function
                try:
                    val = fn_fmt(value, setup=True)
                    c.setParam(key, val, cp)
                    break;

                except:
                    print("You input was invalid for this configuration parameter. Please try again")
                    raise
    ## Save the new config file
    cp.save()


def arg_feed(args, params):
    """ Add feeds, delete feeds, search feeds, enable feeds, disable feeds """

    config = Config(params.config)

    def _add(args):
        ap = ArgumentParser(description="Add a new RSS feed to TwitterBot.", usage="%(prog)s feed add [options]")
        ap.add_argument("-disabled", help="Create the new feed but disable it.", action="store_true")
        ap.add_argument("-tags", help="Hashtags to add to tweets generated from this RSS Feed", nargs="+", type=str)
        ap.add_argument("-order", default=500, help="Adjust the order the feed is checked in relation to other feeds.", type=int)
        ap.add_argument("URL", help="The URL to the Rss Channel you want to create.", type=str)
        _args = ap.parse_args(args)

        try:
            newFeed = db.RssFeed.new(_args.URL, hashtags=_args.tags, order=_args.order, enable=(not _args.disabled))
        except KeyError as k:
            raise Exception("This doesn't look like an RSS Feed", k)

        for backlog in newFeed.get_new_atoms(db.SKIPPED):
            pass
        
        session = db.Session(config.resources.dbschema)
        try:
            session.add(newFeed)
            session.commit()
            print(newFeed)
        except:
            session.rollback()
            raise
        finally:
            session.close()

    def _del(args):
        ap = ArgumentParser(description="Disable or deletes a specific RSS Feed.", usage="%(prog)s feed remove [options]")
        ap.add_argument("-delete", help="Remove the RSS Feed from the database.", action="store_true")
        ap.add_argument("id", help="The ID of the RSS Feed to modify.", type=str)
        _args = ap.parse_args(args)


        session = db.Session(config.resources.dbschema)
        try:
            feed = session.query(db.RssFeed).filter(db.RssFeed.id == _args.id).first()
            if _args.delete:
                session.delete(feed)
            else:
                feed.enable = False
            session.commit()
        except:
            session.rollback()
        finally:
            session.close()

    def _search(args):
        ap = ArgumentParser(description="Seach for a specific RSS Feed.", usage="%(prog)s feed search [options]")
        ap.add_argument("-field", help="Specify the field to search.", default="name", type=str)
        ap.add_argument("PATTERN", help="The pattern to search for (regex).", type=str)
        _args = ap.parse_args(args)

        session = db.Session(config.resources.dbschema)

        try:
            for feed in session.query(db.RssFeed):
                r = re.match(_args.PATTERN, feed.__dict__[_args.field], re.IGNORECASE)
                if(r): print(feed)
        finally:
            session.close()

    def _detail(args):
        ap = ArgumentParser(description="Display details about a specific RSS Feed.", usage="%(prog)s feed detail [options]")
        ap.add_argument("id", help="The ID of the RSS Feed to display.", type=str)
        _args = ap.parse_args(args)

        session = db.Session(config.resources.dbschema)
        try:
            feed = session.query(db.RssFeed).filter(db.RssFeed.id == _args.id).first()
            print("\n {0}".format(feed.name))
            print("-"*(len(feed.url)+14))
            print(" {0:9} : {1}".format("URL",feed.url))
            print(" {0:9} : {1}".format("TAGS", feed.hashtags))
            print(" {0:9} : {1}".format("ENABLED",feed.enable))
            print(" {0:9} : {1}".format("ORDER",feed.order))
            print(" {0:9} : {1}\n".format("ATOMS", len(feed.atoms)))
            
        finally:
            session.close()

    def _enable(args):
        ap = ArgumentParser(description="Enable or disable a specific RSS Feed.", usage="%(prog)s feed enable [options]")
        ap.add_argument("-disable", help="Disable the feed.", action="store_false")
        ap.add_argument("id", help="The ID of the RSS Feed to modify.", type=str)
        _args = ap.parse_args(args)

        session = db.Session(config.resources.dbschema)
        try:
            feed = session.query(db.RssFeed).filter(db.RssFeed.id == _args.id).first()
            feed.enable = _args.disable
            session.commit()
        except:
            session.rollback()
        finally:
            session.close()

    _functions = {
        'add' : _add,
        'remove' : _del,
        'search' : _search,
        'detail' : _detail,
        'enable' : _enable,
    }

    ap = ArgumentParser(description="Manage TwitterBot Feeds", usage="%(prog)s feed [options]")
    ap.add_argument("action", help="Select an operation", choices=_functions)
    ap.add_argument("args", nargs=REMAINDER, help="Arguments for the given operation")
    _args = ap.parse_args(args)
    _functions[_args.action](_args.args)


def arg_joke(args, params):

    config = Config(params.config)

    def _joke_add(args):
        ap = ArgumentParser(description="Add a new joke to TwitterBot.", usage="%(prog)s joke add [options]")
        ap.add_argument("BODY", help="The body of the joke (<140 characters).", type=str)
        _args = ap.parse_args(args)

        try:
            newJoke = db.Joke.new(_args.BODY)
        except:
            raise Exception("Joke body exceeds the maxium size by {0} characters.".format(len(_args.BODY) - 140))

        try:
            session = db.Session(config.resources.dbschema)
            session.add(newJoke)
            session.commit()
            print(newJoke)
        except:
            session.rollback()
            raise
        finally:
            session.close()

    def _joke_del(args):
        ap = ArgumentParser(description="Deletes a specific joke.", usage="%(prog)s joke remove [options]")
        ap.add_argument("id", help="The ID of the joke to remove.", type=str)
        _args = ap.parse_args(args)

        session = db.Session(config.resources.dbschema)
        try:
            joke = session.query(db.Joke).filter(db.Joke.id == _args.id).first()
            session.delete(joke)
            session.commit()
        except:
            session.rollback()
        finally:
            session.close()

    def _joke_search(args):
        ap = ArgumentParser(description="Seach for a specific joke.", usage="%(prog)s joke search [options]")
        ap.add_argument("PATTERN", help="The pattern to search for (regex).", type=str)
        _args = ap.parse_args(args)

        session = db.Session(config.resources.dbschema)

        try:
            for joke in session.query(db.Joke):
                r = re.match(_args.PATTERN, joke.body, re.IGNORECASE)
                if(r): print(joke)
        finally:
            session.close()

    def _joke_detail(args):
        ap = ArgumentParser(description="Display details about a specific Joke.", usage="%(prog)s joke detail [options]")
        ap.add_argument("id", help="The ID of the joke to display.", type=str)
        _args = ap.parse_args(args)

        session = db.Session(config.resources.dbschema)
        try:
            joke = session.query(db.Joke).filter(db.Joke.id == _args.id).first()
            if joke.sent:
                print("\nJoke Details - This joke has been used")
            else:
                print("\nJoke Details")
            print("-"*40)
            print("")
            print(joke.body)
            print("")
            
        finally:
            session.close()

    _functions = {
        'add' : _joke_add,
        'remove' : _joke_del,
        'search' : _joke_search,
        'detail' : _joke_detail,
    }

    ap = ArgumentParser(description="Manage TwitterBot Jokes", usage="%(prog)s joke [options]")
    ap.add_argument("action", help="Select an operation", choices=_functions)
    ap.add_argument("args", nargs=REMAINDER, help="Arguments for the given operation")
    _args = ap.parse_args(args)
    _functions[_args.action](_args.args)


def main(args):

    _functions = {
        "gendb" : arg_install_db,
        "genrc" : arg_genrc,
        "feed" : arg_feed,
        "joke" : arg_joke,
    }

    ap = ArgumentParser(description="RSS Feed TwitterBot", usage="%(prog)s [options]")
    ap.add_argument("-config", help="Specify the config file to use.", type=str, default='~/.twitterbotrc')
    ap.add_argument("action", help="Select an operation", choices=_functions)
    ap.add_argument("args", nargs=REMAINDER, help="Arguments for the given operation")
    _args = ap.parse_args(args)
    _functions[_args.action](_args.args, _args)


if __name__ == "__main__":
    main(argv[1:])
