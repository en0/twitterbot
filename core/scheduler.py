import time

class Scheduler(object):
    def __init__(self, conf):

        self._schedules = []
        for window_start in conf.schedule.window_start:
            self._schedules.append((window_start, conf.schedule.window_duration))

    def get_next_schedule(self, seed):
        today = time.localtime()
        real_schedules = []

        for window_start, window_duration in self._schedules:
            real_window_start = int(time.mktime(time.struct_time(today[:3] + window_start[3:])))

            while seed > real_window_start:
                real_window_start += (24*60*60)

            real_schedules.append((real_window_start, window_duration))

        for window_start, window_duration in sorted(real_schedules):
            if window_start > seed:
                return window_start, window_duration
