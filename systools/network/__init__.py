import socket
import fcntl
import struct
import array
import logging

from systools.system import popen


SOCKET_TIMEOUT = 120


socket.setdefaulttimeout(SOCKET_TIMEOUT)
logger = logging.getLogger(__name__)


def _get_interfaces():
    '''Get network interfaces.

    :return: list
    '''
    max_possible = 128  # arbitrary, raise if needed
    bytes = max_possible * 32
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    names = array.array('B', '\0' * bytes)
    outbytes = struct.unpack('iL', fcntl.ioctl(s.fileno(), 0x8912, struct.pack('iL', bytes, names.buffer_info()[0])))[0]
    namestr = names.tostring()
    return [namestr[i:i + 32].split('\0', 1)[0] for i in range(0, outbytes, 32)]

def _get_interface_ip(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        return socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s', ifname[:15]))[20:24])
    except Exception:
        pass

def get_ip():
    '''Get local IPs.

    :return: list
    '''
    try:
        res = [(i, _get_interface_ip(i)) for i in _get_interfaces()]
    except Exception:
        logger.exception('failed to get local ips')
        return []
    return [ip for i, ip in sorted(res) if not ip.startswith('127.0.')]

def get_hwaddr(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    info = fcntl.ioctl(s.fileno(), 0x8927,  struct.pack('256s', ifname[:15]))
    return ''.join(['%02x:' % ord(char) for char in info[18:24]])[:-1]

def get_hosts():
    '''Get LAN alive hosts.

    :return: list
    '''
    ips = get_ip()
    if not ips:
        return

    res = []
    for ip in ips:
        ip_range = '%s.0/24' % ip.rsplit('.', 1)[0]
        stdout, stderr, return_code = popen(['fping', '-a', '-A', '-r1', '-g', ip_range])
        if return_code is not None:
            res += stdout

    return list(set(res))
