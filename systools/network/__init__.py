import socket
import logging

import netifaces

from systools.system import popen


SOCKET_TIMEOUT = 120

socket.setdefaulttimeout(SOCKET_TIMEOUT)
logger = logging.getLogger(__name__)


def get_ips(with_loopback=False):
    '''Get local IPs.
    '''
    res = []
    for interface in netifaces.interfaces():
        info = netifaces.ifaddresses(interface).get(netifaces.AF_INET)
        if not info:
            continue
        for info_ in info:
            addr = info_.get('addr')
            if not addr:
                continue
            if not with_loopback and addr.startswith('127.'):
                continue
            res.append(addr)
    return res

def is_local(host):
    return socket.gethostbyname(host) in get_ips(True)

def get_hosts():
    '''Get LAN alive hosts.
    '''
    local_ips = get_ips()
    if not local_ips:
        return

    res = []
    for ip in local_ips:
        ip_range = '%s.0/24' % ip.rsplit('.', 1)[0]
        stdout, stderr, return_code = popen(['fping', '-a', '-A', '-r1', '-g', ip_range])
        if return_code is not None:
            res += stdout

    return list(set(res))
