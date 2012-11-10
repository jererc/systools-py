import os
import re
from operator import itemgetter
from stat import S_ISREG, S_ISDIR
import logging

import paramiko

from sshex import Ssh, AuthenticationError, TimeoutError, SshError

from systools.system import PATH_UUIDS, parse_ifconfig, parse_diskutil


RE_SIZE = re.compile(r'^([\d\.]+)([bkmg]*)$', re.I)

logger = logging.getLogger(__name__)
logging.getLogger('paramiko').setLevel(logging.CRITICAL)
logging.getLogger('sshex').setLevel(logging.INFO)


class Host(Ssh):

    def __init__(self, *args, **kwargs):
        super(Host, self).__init__(*args, **kwargs)

        # SFTP client
        transport = paramiko.Transport((self.host, self.port))
        transport.connect(username=self.username, password=self.password)
        self.sftp = paramiko.SFTPClient.from_transport(transport)

    def run_password(self, cmd, password, **kwargs):
        expects = [(r'(?i)\bpassword\b', password)]
        return self.run(cmd, expects=expects, **kwargs)

    def run_ssh(self, cmd, password=None, **kwargs):
        expects = [(r'(?i)\(yes/no\)', 'yes')]
        if password:
            expects.append((r'(?i)\bpassword\b', password))
        return self.run(cmd, expects=expects, **kwargs)

    def listdir(self, path):
        try:
            return [os.path.join(path, f) for f in self.sftp.listdir(path)]
        except IOError:
            return []

    def exists(self, file):
        try:
            self.sftp.lstat(file)
        except IOError:
            return False
        return True

    def isfile(self, file):
        try:
            stat_ = self.sftp.lstat(file)
        except IOError:
            return False
        return S_ISREG(stat_.st_mode)

    def isdir(self, file):
        try:
            stat_ = self.sftp.lstat(file)
        except IOError:
            return False
        return S_ISDIR(stat_.st_mode)

    def walk(self, path, topdown=True):
        for file in self.listdir(path):
            if not self.isdir(file):
                yield 'file', file
            else:
                if topdown:
                    yield 'dir', file
                    for res in self.walk(file, topdown=topdown):
                        yield res
                else:
                    for res in self.walk(file, topdown=topdown):
                        yield res
                    yield 'dir', file

    def remove(self, file):
        '''Remove a file or directory.
        '''
        if not self.isdir(file):
            self.sftp.remove(file)
        else:
            for type, file_ in self.walk(file, topdown=False):
                if type == 'dir':
                    self.sftp.rmdir(file_)
                else:
                    self.sftp.remove(file_)
            self.sftp.rmdir(file)

    def mkdir(self, path):
        try:
            self.sftp.mkdir(path)
        except IOError:
            return
        return True

    def makedirs(self, path):
        path = path.rstrip('/')
        paths = []
        while path.strip('/'):
            paths.insert(0, path)
            path = os.path.dirname(path)
        for path in paths:
            if self.exists(path):
                continue
            if not self.mkdir(path):
                return
        return True

    def download(self, src, dst, callback=None):
        path = os.path.dirname(dst)
        if not os.path.exists(path):
            os.makedirs(path)
        self.sftp.get(src, dst, callback=callback)

    def upload(self, src, dst, callback=None):
        self.makedirs(os.path.dirname(dst))
        self.sftp.put(src, dst, callback=callback)

    def _udisks(self, dev, option, use_sudo=False):
        cmd = 'udisks %s %s' % (option, dev)
        if self.run(cmd, use_sudo=use_sudo)[-1] == 0:
            return True

    def mount(self, dev):
        return self._udisks(dev, '--mount', use_sudo=True)

    def unmount(self, dev):
        return self._udisks(dev, '--unmount', use_sudo=True)

    def get_hostname(self):
        stdout, return_code = self.run('hostname')
        if return_code == 0:
            return stdout[0]

    def get_ifconfig(self):
        stdout = self.run('ifconfig')[0]
        if not stdout:
            return []
        return parse_ifconfig(stdout)

    def _get_diskutils_info(self):
        disks = {}

        output, return_code = self.run('diskutil list -plist', split_output=False)
        if return_code != 0:
            return
        info = parse_diskutil(output, type='list')
        if not info:
            return

        for disk in info:
            output, return_code = self.run('diskutil info -plist %s' % disk, split_output=False)
            if return_code != 0:
                continue

            uuid, dev = parse_diskutil(output, type='info')
            if uuid and dev:
                disks[dev] = {'uuid': uuid, 'dev': dev}

        return disks

    def get_disks(self):
        disks = {}

        # Get devices and uuids
        if self.exists(PATH_UUIDS):
            for line in self.run('ls --color=never -l %s' % PATH_UUIDS)[0][1:]:  # skip details line
                d, uuid, d, link = line.rsplit(None, 3)
                dev = os.path.join('/dev', os.path.basename(link))
                disks[dev] = {'uuid': uuid, 'dev': dev}

        else:
            disks = self._get_diskutils_info() or {}

        # Get mount points
        if disks:
            for line in self.run('mount')[0]:
                dev, d, path, d = line.split(None, 3)
                if dev in disks:
                    disks[dev]['path'] = path

        res = []
        for dev, info in disks.items():
            res.append({
                    'dev': dev,
                    'uuid': info.get('uuid'),
                    'path': info.get('path'),
                    })
        res = sorted(res, key=itemgetter('dev'))
        return res

    def df(self, path=None):
        res = {}
        for line in self.run('df')[0]:
            line = line.split()

            sizes = []
            for val in line:
                size = get_size(val)
                if size is not None:
                    sizes.append(size)
            if len(sizes) != 3:
                continue

            mnt = line[0].split(':')[0]
            res[mnt] = {
                'total': sizes[0],
                'used': sizes[1],
                'available': sizes[2],
                }

        if path:
            try:
                mnt = max([m for m in res if path.startswith(m)])
                return res[mnt]
            except ValueError:
                pass

        return res

    def command_exists(self, cmd):
        if self.run('type -P %s' % cmd)[-1] == 0:
            return True

    def _get_pid(self, cmd):
        stdout, return_code = self.run('ps aux')
        if not stdout:
            return
        for line in stdout:
            line = line.split(None, 10)
            if line and line[-1] == cmd:
                return int(line[1])

    def stop_cmd(self, cmd):
        '''Kill the process if the command is running.
        '''
        self._get_chan()
        pid = self._get_pid(cmd)
        if pid:
            self.run('kill %s' % pid, use_sudo=True)
            return self._get_pid(cmd) is None


def get_size(val):
    '''Get size in MB.
    '''
    res = RE_SIZE.search(val.lower())
    if not res:
        return None

    nb, unit = res.groups()
    if not unit or unit == 'k':
        nb = float(nb) / 1024
    elif unit == 'm':
        nb = float(nb)
    elif unit == 'g':
        nb = float(nb) * 1024
    else:
        nb = float(nb) / 1024 / 1024
    return int(nb)
