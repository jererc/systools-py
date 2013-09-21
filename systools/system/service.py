import re
import logging

from systools.system import popen


RE_SERVICE = {
    'start': re.compile(r'\brunning\b', re.I),
    'stop': re.compile(r'\b(unknown instance|not running)\b', re.I),
    }

logger = logging.getLogger(__name__)


def is_service_running(svc):
    cmd = 'service %s status' % svc
    stdout, stderr, return_code = popen(cmd)
    output = ' '.join((stdout or []) + (stderr or []))
    return RE_SERVICE['start'].search(output) is not None

def set_service(svc, status):
    cmd = 'service %s %s' % (svc, status)
    stdout, stderr, return_code = popen(cmd)
    output = ' '.join((stdout or []) + (stderr or []))
    if return_code == 0 or RE_SERVICE[status].search(output):
        return True
    logger.error('failed to %s service %s: %s' % (status, svc, output))
    return False

def check_service(svc):
    if is_service_running(svc):
        return True
    logger.error('%s service is not running', svc)
    if set_service(svc, 'start'):
        logger.info('started %s service', svc)
        return True
    return False
