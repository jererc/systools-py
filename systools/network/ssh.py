import os
import logging

from pxssh import pxssh

from systools.network import RE_HWADDR
from systools.system import expect_session, PATH_UUIDS


logger = logging.getLogger(__name__)


class Ssh(object):
    def __init__(self, host, username, password=None, timeout=10, port=None, log_errors=True):
        self.host = host
        self.username = username
        self.password = password
        self.logged = False
        self.session = pxssh(timeout=timeout, env={'TERM': 'dumb'})
        try:
            self.session.login(self.host, self.username, self.password, port=port)
            self.logged = True
        except Exception, e:
            if log_errors:
                logger.error('failed to login as %s on %s: %s', username, host, e.value)

    def __del__(self):
        if self.logged:
            self.session.sendcontrol('c')
            self.session.terminate(force=True)
            self.session.logout()

    def popen(self, cmd, passwords=None, timeout=30):
        '''Execute a command on the host.

        :param passwords: expected password(s)
        :param timeout: command timeout (seconds)

        :return: tuple (stdout, return code)
        '''
        stdout = []
        return_code = None
        self.session.sendline(cmd)
        res = expect_session(self.session, cmd=cmd, host=self.host, passwords=passwords, timeout=timeout)
        if res:
            # Get the stdout and exit status
            stdout = self.session.before.splitlines()[1:]  # skip the command line
            self.session.sendline('echo $?')    # get the command exit status code
            self.session.prompt()
            try:
                return_code = int(self.session.before.splitlines()[-1])
            except Exception:
                logger.error('failed to get the return code for command "%s" on host %s: "%s"', cmd, self.host, self.session.before)
        return stdout, return_code


class Host(Ssh):

    def get_disks(self):
        disks = {}
        if self.path_exists(PATH_UUIDS):
            for line in self.popen('ls --color=never -l %s' % PATH_UUIDS)[0][1:]:  # skip details line
                d, uuid, d, link = line.rsplit(None, 3)
                dev = os.path.join('/dev', os.path.basename(link))
                disks[uuid] = {'dev': dev}
        else:
            # TODO: handle mac os
            pass

        # Get mount points
        for line in self.popen('mount')[0]:
            dev, d, path, d = line.split(None, 3)
            for uuid, info in disks.items():
                if info['dev'] == dev:
                    disks[uuid]['path'] = path
        return disks

    def get_disk_usage(self, path=None, uuid=None):
        if uuid:
            path = self.get_disks(uuid)

        output = self.popen('df')[0][1:]
        res = {}
        for index, line in enumerate(output):
            fields = line.split()
            if len(fields) == 1:  # handle newline after long filesystem name
                fields = [fields[0][:-1]] + output[index + 1].split()
                del output[index + 1]
            elif len(fields) != 6:
                logger.error('failed to parse df output line: "%s" (output: %s)', line, output)
                continue

            filesystem, d, used, available, percentage, mount = fields
            if path and mount != path:
                continue
            res[mount] = {
                'filesystem': filesystem,
                'used': used,
                'available': available,
                }
        return res

    def _udisks(self, dev, option):
        cmd = 'sudo udisks %s %s' % (option, dev)
        if self.popen(cmd, passwords=self.password)[1] == 0:
            return True

    def mount(self, dev):
        return self._udisks(dev, '--mount')

    def unmount(self, dev):
        return self._udisks(dev, '--unmount')

    def get_hwaddr(self):
        res = []
        for line in self.popen('ifconfig')[0]:
            r = RE_HWADDR.search(line)
            if r:
                res.append(r.group(1))
        return res

    def get_hostname(self):
        return self.popen('hostname')[0][0]

    def command_exists(self, command):
        if self.popen('type -P %s' % command)[1] == 0:
            return True

    def path_exists(self, path):
        if self.popen('test -d %s' % path)[1] == 0:
            return True

    def mkdir(self, path, sudo=False):
        '''Create the path.
        '''
        cmd = '%smkdir -p %s' % ('sudo ' if sudo else '', path)
        if self.popen(cmd, passwords=self.password)[1] == 0:
            return True
