from time import time

class StopWatch(object):
    def __init__(self, seed=0):
        self._start = seed

    def start(self):
        self._start = int(time())

    def lap(self):
        s = int(time())
        r = s - self._start
        self._start = s
        return r

    def peek(self):
        return int(time()) - self._start
