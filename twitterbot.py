#!/usr/bin/env python2
from argparse import ArgumentParser, REMAINDER
from threading import Thread, Event, Lock
from Queue import Queue, Empty
from core import db, Config, StopWatch, formatter, Scheduler
from time import sleep, time
from sys import argv as args
from signal import signal, SIGINT
import bitly_api
import twitter
import socket

socket.setdefaulttimeout(20)

def feed(config, out_queue, pflag, cflag, session_mutex):
    sw = StopWatch()

    pflag.wait()
    cflag.set()

    try:
        while pflag.isSet():

            if sw.peek() < config.threads.atom_query_delta:
                sleep(5)
                continue

            sw.lap()

            print("FEED: Checking for new atoms...")
            with session_mutex:
                session = db.Session(config.resources.dbschema)
                for feed in session.query(db.RssFeed).order_by('`order`'):
                    print("FEED: [{0}] searching...".format(feed.name))
                    sleep(5)
                    _atom_count = 0
                    for atom in feed.get_new_atoms(db.RECIEVED): 
                        out_queue.put(atom)
                        session.commit()
                        _atom_count += 1
                    print("FEED: [{0}] Found {1} new atoms.".format(feed.name, _atom_count))
                session.close()
            print("FEED: Sleeping for next cycle")

    finally:
        print("Exiting Feed Reader")
        cflag.clear()


from datetime import datetime
def schedule(config, in_queue, out_queue, pflag, cflag, session_mutex):

    scheduler = Scheduler(config)
    seed = int(time())

    pflag.wait()
    cflag.set()
    while pflag.isSet() or not in_queue.empty():

        ## Get scheduling window
        window_start, window_duration = scheduler.get_next_schedule(seed)

        ## Calculate step between each tweet in window
        step = window_duration / config.tweet_quota.count

        ## Calculate the new seed and end of this window
        window_end = seed = window_start + window_duration

        ## Clear the schedule list
        schedules = []

        ## Fill new schedule list with calculated values
        for timestamp in range(window_start, window_end, step):
            schedules.append(timestamp)

        ## Use each schedule in this window but watch for exit notice
        while len(schedules) > 0 and (pflag.isSet() or not in_queue.empty()):

            new_schedule = schedules.pop(0)

            ## Assign the atom in the queue but verify it will not expire
            ## before it would be sent. If it will, drop it and move on.
            while new_schedule and (pflag.isSet() or not in_queue.empty()):

                ## Verify the schedule is still good. (if the queue blocks and we miss our window)
                if new_schedule <= int(time()):
                    new_schedule = None
                    continue

                try:
                    ## Get the next atom
                    i = in_queue.get(timeout=10)

                    ## Validate the schedule and skip if it is out of range
                    if new_schedule - i['recv'] > config.tweet_quota.expire_delta:
                        print("SCHEDULER: Atom expired before schedule event.")
                        with session_mutex:
                            session = db.Session(config.resources.dbschema)
                            db.Atom.set_state(db.DROPPED, i['ident'], session)
                            session.commit()
                            session.close()
                        continue

                    ## Schedule was ok, apply it, clear the schedule flag, and queue for tweeting
                    i['schedule'] = new_schedule
                    new_schedule = None
                    
                    with session_mutex:
                        session = db.Session(config.resources.dbschema)
                        db.Atom.set_state(db.SCHEDULED, i['ident'], session)
                        session.commit()
                        session.close()

                    out_queue.put(i)

                except Empty:
                    sleep(0)

    print("Exiting Scheduler")
    cflag.clear()


def fmt(config, in_queue, out_queue, pflag, cflag, session_mutex):
    x = []
    pflag.wait()
    cflag.set()

    _bitly = bitly_api.Connection(config.bitly_keys.user, access_token=config.bitly_keys.key)

    while pflag.isSet() or not in_queue.empty():
        try:
            i = in_queue.get(timeout=10)
            print("FORMATTER: Recieving new atom")

            ## Get Bitly Address
            bitly_short_link = _bitly.shorten(i['link'])
            if not bitly_short_link: continue

            i['short_link'] = bitly_short_link['url']

            msg = formatter.format_atom(i, config)

            with session_mutex:
                session = db.Session(config.resources.dbschema)
                db.Atom.set_state(db.FORMATTED, i['ident'], session)
                db.Atom.set_bitly(i['short_link'], i['ident'], session)
                session.commit()
                session.close()

            out_queue.put((msg, i['schedule'], i['ident']))

        except Empty:
            sleep(0)

    print("Exiting Formatter")
    cflag.clear()


def tweet(config, in_queue, flag, session_mutex):

    oauth_token, oauth_secret = twitter.read_token_file(config.twitter_keys.cred_path)
    _twitter = twitter.Twitter(auth=twitter.OAuth(oauth_token, oauth_secret, config.twitter_keys.key, config.twitter_keys.secret))
    
    def send_tweet(body):
        print("TWEET: Posting tweet...")
        _twitter.statuses.update(status=body)
        print("TWEET: Complete")
        
    count = 0
    flag.wait()
    while flag.isSet() or not in_queue.empty():
        try:
            msg, schedule, uid = in_queue.get(timeout=10)
            count += 1

            print("\nTWEET ATOM: {0}".format(datetime.fromtimestamp(schedule).strftime("%H:%M:%S %m-%d-%Y")))

            with session_mutex:
                session = db.Session(config.resources.dbschema)
                db.Atom.set_state(db.WAIT, uid, session)
                session.commit()
                session.close()

            ## Wait for schedule it hit
            while int(time()) < schedule:
                if not flag.isSet(): 
                    print("TWEET: Warning: Exiting with scheduled tweets. Oh well")
                    return
                else:
                    sleep(1)

            send_tweet(msg)

            with session_mutex:
                session = db.Session(config.resources.dbschema)
                db.Atom.set_state(db.SENT, uid, session)
                session.commit()
                session.close()

            sleep(config.tweet_quota.delta)

            if (count % config.tweet_quota.joke_align) == 0:

                with session_mutex:
                    session = db.Session(config.resources.dbschema)
                    joke = db.Joke.get_next(session)
                    if joke:
                        print("SENDING A JOKE")
                        send_tweet(joke.body)
                        session.commit()
                        sleep(config.tweet_quota.delta)
                    session.close()

        except Empty:
            sleep(0)
    
    print("Exiting Tweet Engine.")


def create_thread_plan(config):
    pFlag = Event()
    schdFlag = Event()
    fmtFlag = Event()
    tweetFlag = Event()
    session_lock = Lock()

    schdQueue = Queue(maxsize=config.threads.queue_size)
    fmtQueue = Queue(maxsize=config.threads.queue_size)
    tweetQueue = Queue(maxsize=config.threads.queue_size)

    return {
        'feedThread': ( feed, dict( config=config, out_queue=schdQueue, pflag=pFlag, cflag=schdFlag, session_mutex=session_lock )),
        'schdThread': ( schedule, dict( config=config, in_queue=schdQueue, out_queue=fmtQueue, 
                                        pflag=schdFlag, cflag=fmtFlag, session_mutex=session_lock )),
        'fmtThread': ( fmt, dict( config=config, in_queue=fmtQueue, out_queue=tweetQueue, 
                                  pflag=fmtFlag, cflag=tweetFlag, session_mutex=session_lock )),
        'tweetThread': ( tweet, dict( config=config, in_queue=tweetQueue, flag=tweetFlag, session_mutex=session_lock )),
    }, pFlag


def start_threads(thread_plan):
    threads = []
    for tname,(fn,kwargs) in thread_plan.items():
        newThread = Thread(name=tname, kwargs=kwargs, target=fn)
        threads.append(newThread)
        newThread.start()
    return threads


def wait_threads(threads):
    for thread in threads:
        while(thread.isAlive()):
            sleep(1)


def __signal(pflag):
    def _signal_wrapper(signum, frame):
        print("\b\bCaught signal. Waiting for queues to empty...")
        pflag.clear()
    return _signal_wrapper;


if __name__ == "__main__":
    ap = ArgumentParser(description="RSS Feed TwitterBot", usage="%(prog)s [options]")
    ap.add_argument("-config", help="Specify the config file to use.", type=str, default='~/.twitterbotrc')
    _args = ap.parse_args(args[1:])
    config = Config(_args.config)

    tp, pflag = create_thread_plan(config)

    signal(SIGINT, __signal(pflag))

    th = start_threads(tp)
    pflag.set()

    wait_threads(th)

