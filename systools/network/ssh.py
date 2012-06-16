import os.path
from operator import itemgetter
import logging

from sshex import Ssh

from systools.system import PATH_UUIDS, parse_ifconfig, parse_diskutil


logger = logging.getLogger(__name__)
logging.getLogger('paramiko').setLevel(logging.ERROR)
logging.getLogger('sshex').setLevel(logging.INFO)


class Host(Ssh):

    def run_password(self, cmd, password, **kwargs):
        expects = [(r'(?i)\bpassword\b', password)]
        return self.run(cmd, expects=expects, **kwargs)

    def run_ssh(self, cmd, password=None, **kwargs):
        expects = [(r'(?i)\(yes/no\)', 'yes')]
        if password:
            expects.append((r'(?i)\bpassword\b', password))

        return self.run(cmd, expects=expects, **kwargs)

    def command_exists(self, cmd):
        if self.run('type -P %s' % cmd)[-1] == 0:
            return True

    def path_exists(self, path):
        if self.run('test -d %s' % path)[-1] == 0:
            return True

    def mkdir(self, path, use_sudo=False):
        cmd = 'mkdir -p %s' % path
        if self.run(cmd, use_sudo=use_sudo)[-1] == 0:
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
        return self.run('hostname')[0][0]

    def get_ifconfig(self):
        stdout = self.run('ifconfig')[0]
        return parse_ifconfig(stdout)

    def _get_diskutils_info(self):
        disks = {}

        output = self.run('diskutil list -plist', split_output=False)[0]
        if not output:
            return
        info = parse_diskutil(output, type='list')
        if not info:
            return

        for disk in info:
            output = self.run('diskutil info -plist %s' % disk, split_output=False)[0]
            if not output:
                continue

            uuid, dev = parse_diskutil(output, type='info')
            if uuid and dev:
                disks[dev] = {'uuid': uuid, 'dev': dev}

        return disks

    def get_disks(self):
        disks = {}

        # Get devices and uuids
        if self.path_exists(PATH_UUIDS):
            for line in self.run('ls --color=never -l %s' % PATH_UUIDS)[0][1:]:  # skip details line
                d, uuid, d, link = line.rsplit(None, 3)
                dev = os.path.join('/dev', os.path.basename(link))
                disks[dev] = {'uuid': uuid, 'dev': dev}

        else:
            disks = self._get_diskutils_info() or {}

        if disks:
            # Get mount points
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
