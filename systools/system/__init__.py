import os
import re
import time
from datetime import timedelta
import subprocess
from functools import wraps
import signal
import inspect
from operator import itemgetter
import imp
import logging

from lxml import etree


PATH_UUIDS = '/dev/disk/by-uuid'
RE_HWADDR = re.compile(r'\b(%s)\b' % ':'.join(['[0-9a-f]{2}'] * 6), re.I)

logger = logging.getLogger(__name__)


class TimeoutError(Exception): pass


class dotdict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def timeout(seconds=0, minutes=0, hours=0, **parameters):
    '''Return defaut of raise if the timeout is reached.
    '''
    delay = seconds + 60 * minutes + 3600 * hours

    def decorator(func):
        def _handle_timeout(signum, frame):
            raise TimeoutError('timeout reached (%s seconds)' % delay)

        def wrapper(*args, **kwargs):
            signal.signal(signal.SIGALRM, _handle_timeout)
            signal.alarm(delay)
            try:
                result = func(*args, **kwargs)
            except TimeoutError, e:
                if 'return_value' not in parameters:
                    raise
                result = parameters['return_value']
                logger.error(str(e))
            finally:
                signal.alarm(0)
            return result
        return wraps(func)(wrapper)
    return decorator

def loop(seconds=0, minutes=0, hours=0):
    '''Loop the decorated function with a delay.
    '''
    delay = seconds + 60 * minutes + 3600 * hours

    def decorator(func):
        def wrapper(*args, **kwargs):
            while True:
                try:
                    func(*args, **kwargs)
                except Exception:
                    logger.exception('exception')
                time.sleep(delay)
        return wraps(func)(wrapper)
    return decorator

def timer(duration_min=5):
    '''Log the duration of the decorated function.
    '''
    def decorator(func):
        def wrapper(*args, **kwargs):
            time_start = time.time()
            result = func(*args, **kwargs)

            duration = int(time.time() - time_start)
            if duration >= duration_min:
                module_file = inspect.getfile(func)
                module_name = '%s.%s' % (os.path.splitext(os.path.basename(module_file))[0], func.__name__)
                logging.getLogger(module_name).debug('processed in %s (args: %s, %s)', str(timedelta(seconds=duration)), str(args), str(kwargs))

            return result
        return wraps(func)(wrapper)
    return decorator

def popen(cmd, cwd=None, shell=False):
    '''Execute a command.

    :return: tuple (stdout, stderr, return code)
    '''
    if not shell and not isinstance(cmd, (list, tuple)):
        cmd = cmd.split()

    try:
        proc = subprocess.Popen(cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=cwd, shell=shell)
        stdout, stderr = proc.communicate()
        return stdout.splitlines(), stderr.splitlines(), proc.returncode
    except Exception, e:
        logger.exception('failed to execute command "%s": %s', ' '.join(cmd), str(e))
        return None, None, None

def udisks(dev, option):
    if popen(['udisks', option, dev])[-1] == 0:
        return True

def parse_ifconfig(output):
    info = {}
    ifname = None
    for line in output:
        lsplit = line.split()
        if line and line[0] not in (' ', '\t'):
            ifname = lsplit[0].split(':')[0]
            info.setdefault(ifname, {})

        if ifname:
            res = RE_HWADDR.search(line)
            if res:
                info[ifname]['hwaddr'] = res.group(1)

            if len(lsplit) > 1 and lsplit[0] == 'inet':
                info[ifname]['ip'] = lsplit[1].split(':')[-1]

    res = []
    for ifname, data in info.items():
        if data.get('hwaddr'):
            res.append({
                    'ifname': ifname,
                    'ip': data.get('ip'),
                    'hwaddr': data['hwaddr'],
                    })
    return sorted(res, key=itemgetter('ifname'))

def parse_diskutil(output, type='list'):
    dict_ = etree.fromstring(output)[0]

    if type == 'list':
        disks = []
        for index, el in enumerate(dict_):
            if el.text == 'AllDisks':
                for disk in dict_[index + 1]:
                    disks.append(disk.text)
        return disks

    elif type == 'info':
        uuid = None
        dev = None
        for index, el in enumerate(dict_):
            if el.text == 'DeviceNode':
                dev = dict_[index + 1].text.lower()
                if not dev.startswith('/dev'):
                    dev = os.path.join('/dev', dev)
            elif el.text == 'VolumeUUID':
                uuid = dict_[index + 1].text.lower()
        return uuid, dev

def get_package_modules(package_name):
    res = []
    file, path, description = imp.find_module(package_name)
    for module in os.listdir(path):
        filename, ext = os.path.splitext(module)
        if ext.lower() == '.py':
            res.append(filename)
    return res

def check_commands(cmds):
    res = True
    for cmd in cmds:
        if popen('which %s' % cmd)[-1] != 0:
            res = False
            logger.error('%s is missing', cmd)
    return res
