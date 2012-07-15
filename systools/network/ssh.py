import os.path
import re
from operator import itemgetter
from stat import S_ISDIR
import logging

from sshex import Ssh, AuthenticationError, TimeoutError, SshError
from sftpsync import Sftp

from systools.system import PATH_UUIDS, parse_ifconfig, parse_diskutil


RE_SIZE = re.compile(r'^([\d\.]+)([bkmg]*)$', re.I)


logger = logging.getLogger(__name__)
logging.getLogger('paramiko').setLevel(logging.CRITICAL)
logging.getLogger('sshex').setLevel(logging.INFO)
logging.getLogger('sftpsync').setLevel(logging.INFO)


class Host(Ssh):
    def __init__(self, *args, **kwargs):
        super(Host, self).__init__(*args, **kwargs)
        self.sftp = self.client.open_sftp()

    def run_password(self, cmd, password, **kwargs):
        expects = [(r'(?i)\bpassword\b', password)]
        return self.run(cmd, expects=expects, **kwargs)

    def run_ssh(self, cmd, password=None, **kwargs):
        expects = [(r'(?i)\(yes/no\)', 'yes')]
        if password:
            expects.append((r'(?i)\bpassword\b', password))

        return self.run(cmd, expects=expects, **kwargs)

    def exists(self, path):
        if self.run('ls %s' % path)[-1] == 0:
            return True

    def command_exists(self, cmd):
        if self.run('type -P %s' % cmd)[-1] == 0:
            return True

    def mkdir(self, path, use_sudo=False):
        if self.run('mkdir %s' % path, use_sudo=use_sudo)[-1] == 0:
            return True

    def makedirs(self, path, use_sudo=False):
        paths = []
        while path not in ('/', ''):
            paths.insert(0, path)
            path = os.path.dirname(path)

        for path in paths:
            if not self.exists(path) \
                    and not self.mkdir(path, use_sudo=use_sudo):
                return

        return True

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

    def listdir(self, path):
        return [os.path.join(path, f) for f in self.sftp.listdir(path)]

    def is_dir(self, file):
        return S_ISDIR(self.sftp.lstat(file).st_mode)

    def walk(self, path, topdown=True):
        for file in self.listdir(path):
            if not self.is_dir(file):
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
        if not self.is_dir(file):
            self.sftp.remove(file)
        else:
            for type, file_ in self.walk(file, topdown=False):
                if type == 'dir':
                    self.sftp.rmdir(file_)
                else:
                    self.sftp.remove(file_)

            self.sftp.rmdir(file)

    def sftpsync(self, *args, **kwargs):
        sftp = Sftp(self.host, self.username, self.password, port=self.port)
        sftp.sync(*args, **kwargs)


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
