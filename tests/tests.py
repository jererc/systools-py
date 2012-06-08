#!/usr/bin/env python
import os
import os.path
import logging

try:
    import unittest2 as unittest
except ImportError:
    import unittest

from settings import USERNAME, PASSWORD

from systools.system import popen_expect
from systools.network.ssh import Host


FILE_HOSTS = os.path.join(os.environ['HOME'], '.ssh/known_hosts')


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('tests')


class ExpectLocalTest(unittest.TestCase):

    def setUp(self):
        try:
            os.remove(FILE_HOSTS)
        except:
            pass
        assert not os.path.exists(FILE_HOSTS)

    def test_sudo_password(self):
        cmd = 'sudo whoami'

        stdout, return_code = popen_expect(cmd)
        self.assertFalse(stdout)
        self.assertFalse(return_code)

        stdout, return_code = popen_expect(cmd, passwords=PASSWORD)
        self.assertEquals(stdout[0], 'root')
        self.assertEquals(return_code, 0)

    def test_ssh_password(self):
        cmd = 'ssh %s@localhost whoami' % USERNAME

        stdout, return_code = popen_expect(cmd)
        self.assertFalse(stdout)
        self.assertFalse(return_code)

        stdout, return_code = popen_expect(cmd, passwords=PASSWORD)
        self.assertEquals(stdout[0], USERNAME)
        self.assertEquals(return_code, 0)

    def test_ssh_sudo_command(self):
        cmd = 'ssh -t %s@localhost sudo whoami' % USERNAME

        stdout, return_code = popen_expect(cmd, passwords=[PASSWORD, PASSWORD])
        self.assertEquals(stdout[0], 'root')
        self.assertEquals(return_code, 0)

    def test_ssh_command_ssh(self):
        cmd = 'ssh -t %s@localhost ssh %s@localhost whoami' % (USERNAME, USERNAME)

        stdout, return_code = popen_expect(cmd, passwords=[PASSWORD, PASSWORD])
        self.assertEquals(stdout[0], USERNAME)
        self.assertEquals(return_code, 0)

    def test_ssh_sudo_command_ssh(self):
        cmd = 'ssh -t %s@localhost ssh -t %s@localhost sudo whoami' % (USERNAME, USERNAME)

        stdout, return_code = popen_expect(cmd, passwords=[PASSWORD, PASSWORD, PASSWORD])
        self.assertEquals(stdout[0], 'root')
        self.assertEquals(return_code, 0)


class ExpectRemoteTest(unittest.TestCase):

    def setUp(self):
        try:
            os.remove(FILE_HOSTS)
        except:
            pass
        assert not os.path.exists(FILE_HOSTS)

    def test_password(self):
        host = Host('localhost', USERNAME, 'wrong_password')
        self.assertFalse(host.logged)

        host = Host('localhost', USERNAME, PASSWORD)
        self.assertTrue(host.logged)

    def test_sudo_password(self):
        host = Host('localhost', USERNAME, PASSWORD)

        stdout, return_code = host.popen('sudo whoami', passwords=[PASSWORD])
        self.assertEquals(stdout[0], 'root')
        self.assertEquals(return_code, 0)


if __name__ == '__main__':
    unittest.main()
