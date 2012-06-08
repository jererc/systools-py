import os
import re
import time
from datetime import timedelta
import subprocess
from functools import wraps
import signal
from glob import glob
import inspect
import logging

import pexpect


RE_PASSWORD = re.compile(r'\b(password|mot de passe).*:\W*', re.I)
RE_SSH_AUTH = re.compile(r'continue connecting \(yes/no\).*', re.I)
RE_SSH_OFFENDING = re.compile(r'Offending[\w\s]+key\sin\s([^\s]*known_hosts).*', re.I)
PATH_UUIDS = '/dev/disk/by-uuid'


logger = logging.getLogger(__name__)


class TimeoutError(Exception): pass


def timeout(seconds=0, minutes=0, hours=0):
    '''Raise an exception if the decorated function has not finished processing
    before the timeout.
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
                logging.getLogger(module_name).debug('processed in %s', timedelta(seconds=duration))

            return result
        return wraps(func)(wrapper)
    return decorator

def get_log_lines(file, lines_max=100):
    '''Get the reversed rotated log files lines.

    :param file: log file
    :param lines_max: maximum log lines to get

    :return: list
    '''
    lines = []
    for log_file in sorted(glob(file + '*')):
        with open(log_file) as fd:
            lines += reversed(fd.read().splitlines())
        if len(lines) >= lines_max:
            break
    return lines[:lines_max]

def popen(cmd, cwd=None):
    '''Execute a command.

    :return: tuple (stdout, stderr, return code)
    '''
    if not isinstance(cmd, (list, tuple)):
        cmd = cmd.split()

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
        stdout, stderr = proc.communicate()
        return stdout.splitlines(), stderr.splitlines(), proc.returncode
    except Exception, e:
        logger.exception('failed to execute command "%s": %s' % (' '.join(cmd), e))
        return None, None, None

def expect_session(session, cmd, host=None, passwords=None, timeout=30):
    '''Interact with a pexpect cmd.

    :param session: pexpect session
    :param cmd: command to execute
    :param host: hostname for a remote session, None for a local session
    :param passwords: expected password(s)
    :param timeout: command timeout (seconds)
    '''
    if passwords and not isinstance(passwords, (list, tuple)):
        passwords = [passwords]

    prompt = re.compile(session.PROMPT) if host else pexpect.EOF
    host_msg = ' on host %s' % host or ''

    while True:
        res = session.expect_list([RE_SSH_AUTH, RE_SSH_OFFENDING, RE_PASSWORD, pexpect.TIMEOUT, prompt], timeout=timeout)
        if res == 0:
            session.sendline('yes')
        elif res == 1:
            file_hosts = RE_SSH_OFFENDING.search(session.after).group(1)
            session.sendline('%srm %s' % ('sudo ' if file_hosts.startswith('/root/') else '', file_hosts))
            session.expect(prompt)
            logger.error('ssh error for command "%s"%s: offending ssh key in %s', cmd, host_msg, file_hosts)
            return
        elif res == 2:
            if not passwords:
                logger.error('password required for command "%s"%s', cmd, host_msg)
                return
            session.sendline(passwords.pop(0))
        elif res == 3:
            logger.error('timeout reached (%s seconds) for command "%s"%s', timeout, cmd, host_msg)
            return
        else:
            return True

def popen_expect(cmd, passwords=None, timeout=30):
    '''Execute a command and expect passwords or ssh actions.

    :param passwords: expected password(s)
    :param timeout: command timeout (seconds)

    :return: tuple (stdout, return code)
    '''
    stdout = []
    return_code = None
    try:
        session = pexpect.spawn(cmd, timeout=timeout, env={'PATH': os.environ['PATH'], 'TERM': 'dumb'})   # TERM=dumb to avoid stdout colors
    except pexpect.ExceptionPexpect:
        logger.exception('exception')
    else:
        try:
            res = expect_session(session, cmd=cmd, passwords=passwords, timeout=timeout)
            if res:
                # Get the stdout and exit status
                session.close(force=True)
                stdout = session.before.splitlines()
                if stdout:
                    while stdout and not stdout[0]:    # remove carriage returns from sent passwords
                        stdout.pop(0)
                return_code = session.exitstatus
        finally:
            session.terminate(force=True)   # clean open process
    return stdout, return_code

def is_file_open(value):
    '''Check if a file which name contains the string is open.
    '''
    stdout, stderr, return_code = popen(['lsof', '-F', 'n', '/'])
    if return_code:
        return

    re_incl = re.compile(r'%s' % re.escape(value))
    for line in stdout:
        if re_incl.search(line):
            return True

def get_disks():
    # Get mount points
    mounts = {}
    for line in popen('mount')[0]:
        dev, d, path = line.split()[:3]
        mounts[dev] = path

    # Get uuids and devices
    res = {}
    for uuid in os.listdir(PATH_UUIDS):
        link = os.path.join(PATH_UUIDS, uuid)
        dev = os.path.abspath(os.path.join(os.path.dirname(link), os.readlink(link)))
        if dev in mounts:
            res[uuid] = {
                'dev': dev,
                'path': mounts[dev],
                }
    return res

def udisks(dev, option):
    stdout, stderr, return_code = popen(['udisks', option, dev])
    if return_code == 0:
        return True


class dotdict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__
