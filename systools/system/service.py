import re
import logging

from systools.system import popen


RE_SERVICE = {
    'start': re.compile(r'\brunning\b', re.I),
    'stop': re.compile(r'\b(unrecognized|unknown instance|not running)\b', re.I),
    }

logger = logging.getLogger(__name__)


def _service(svc, param):
    cmd = 'service %s %s' % (svc, param)
    stdout, stderr, returncode = popen(cmd)
    return ' '.join((stdout or []) + (stderr or [])), returncode

def _set_service(svc, status):
    output, returncode = _service(svc, status)
    if returncode == 0 or RE_SERVICE[status].search(output):
        return True
    logger.error('failed to %s service %s: %s', status, svc, output)
    return False

def is_running(svc):
    output, returncode = _service(svc, 'status')
    return RE_SERVICE['start'].search(output) is not None

def start(svc):
    return _set_service(svc, 'start')

def stop(svc):
    return _set_service(svc, 'stop')

def check_service(svc, do_start=True):
    if is_running(svc):
        return True
    logger.error('%s service is not running', svc)
    if do_start and start(svc):
        logger.info('started %s service', svc)
        return True
    return False
