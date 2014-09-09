import time
import datetime

def format_to_utcts(val, fmt):
    return int(time.mktime(time.strptime(val, fmt)) - time.mktime((1970, 1, 1, 0, 0, 0, 0, 0, 0)))

def utcts_to_format(ts, fmt):
    return datetime.datetime.utcfromtimestamp(ts).strftime(fmt)

