import ConfigParser
from os.path import isfile, expanduser, abspath
import time


def _classFactory(name, section, params):

    class ConfigBase(object):
        def __init__(self, classtype):
            self._type = classtype

        @staticmethod
        def getSection():
            return section

        @staticmethod
        def getParams():
            return params
            
        @staticmethod
        def setParam(name, value, cp):
            if not cp.has_section(section):
                cp.add_section(section)

            for key,fn_fmt in params:
                if name != key: continue
                cp.set(section, key, str(value))
                return

            raise ConfigParser.NoOptionError("Invalid option '{0}' for section '{1}'".format(name, section))
                
    def __init__(self, cp):
        for key,fn_fmt in params:
            try:
                val = cp.get(section, key)
                setattr(self, key, fn_fmt(val))
            except ConfigParser.NoOptionError:
                raise KeyError("Missing required parameter '{0}' in section '{1}'".format(key, section))
            except ValueError:
                raise ValueError("Invalid format for parameter '{0}' in section '{1}'".format(key,section))

        ConfigBase.__init__(self,name[:-len("Class")])

    newclass = type(name, (ConfigBase,),{"__init__":__init__})
    return newclass

def _bool(s, setup=False):
    """A True or False value"""
    if setup and s.lower() == "true":
        return True
    elif setup and s.lower() == "false":
        return False
    elif setup:
        raise ValueError("Valid values are 'True' and 'False'")

    return bool(s)

def _int(s, setup=False):
    """A integer value"""
    return int(s)

def _str(s, setup=False):
    """A clear text string"""
    return str(s)

def _time_list(s, setup=False):
    """A string representing a time. HH:MM:SS"""
    v = []
    for i in s.split(' '):
        v.append(time.strptime(i, "%H:%M:%S"))
    if setup: return s
    return v

def _path_ghost(s, setup=False):
    """A filesystem path to the resource"""
    _s = expanduser(s)
    return abspath(_s)

def _path(s, setup=False):
    """A filesystem path to the resource"""
    _s = expanduser(s)
    if not setup and not isfile(_s):
        raise Exception("File '{0}' was not found".format(_s))
    return abspath(_s)
    
_configClasses = {
    'SCHEDULE' : _classFactory("ScheduleConfigClass", "SCHEDULE", [
                    ("dynamic_enabled", _bool), 
                    ("window_start", _time_list),
                    ("window_duration", _int)
                ]),
    'TWEET_QUOTA' : _classFactory("QuotaConfigClass", "TWEET_QUOTA", [
                    ("count", _int), 
                    ("delta", _int),
                    ("joke_align", _int),
                    ("expire_delta", _int)
                ]),
    'TWITTER_KEYS' : _classFactory("TwitterKeysConfigClass", "TWITTER_KEYS", [
                    ("app", _str),
                    ("cred_path", _path), 
                    ("key", _str),
                    ("secret", _str)
                ]),
    'BITLY_KEYS' : _classFactory("BitlyKeysConfigClass", "BITLY_KEYS", [
                    ("user", _str), 
                    ("key", _str),
                ]),
    'CALAIS_KEYS' : _classFactory("BitlyKeysConfigClass", "CALAIS_KEYS", [
                    ("key", _str),
                ]),
    'RESOURCES' : _classFactory("ResourcesConfigClass", "RESOURCES", [
                    ("dbschema", _str),
                    ("pidfile", _path_ghost),
                ]),
    'THREADS' : _classFactory("ThreadConfigClass", "THREADS", [
                    ("queue_size", _int),
                    ("atom_query_delta", _int),
                ]),
}

class Config(object):

    path = None

    def __init__(self, path, autoload=True):
        self.path = abspath(expanduser(path))
        if autoload: self.load()

    def create(self):
        """ Create a new configrc file.

        Returns:
            a tuple (ConfigParser, Params)
            The params is an array of tupes (key, format_function)

        Raises:
            ValueError
        """
        cp = ConfigParser.ConfigParser()

        def _iter():
            for s in sorted(_configClasses):
                yield _configClasses[s]

        def _save():
            with open(self.path, "w") as fid:
                cp.write(fid)

        setattr(cp, "save", _save)
        return cp, _iter
        

    def load(self, path=None):
        if not path: path = self.path
        else: self.path = abspath(expanduser(path))

        cp = ConfigParser.ConfigParser()
        cp.read(path)

        for s in cp.sections():
            if s not in _configClasses:
                raise KeyError("Unknown section '{0}' in configuration file".format(s))
            setattr(self, s.lower(), _configClasses[s](cp))
