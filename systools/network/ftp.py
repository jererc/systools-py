import os
from ftplib import FTP, error_perm
import logging


logger = logging.getLogger(__name__)


class FtpError(Exception): pass


class Ftp(object):

    def __init__(self, host, username, password, port=21):
        try:
            self.ftp = FTP()
            self.ftp.connect(host, port)
            self.ftp.login(username, password)
        except Exception, e:
            raise FtpError(str(e))

    def __del__(self):
        try:
            self.ftp.quit()
        except Exception:
            pass

    def close(self):
        try:
            self.ftp.quit()
        except Exception:
            pass

    def exists(self, path):
        if not self.isfile(path):
            try:
                self.cwd(path)
            except FtpError:
                return False
        return True

    def isfile(self, path):
        try:
            self.ftp.size(path)
        except error_perm:
            return False
        return True

    def listdir(self, path):
        self.cwd(path)
        res = self.ftp.nlst()
        return [os.path.basename(r) for r in res]

    def walk(self, path, topdown=True):
        if self.isfile(path):
            yield 'file', path
        else:
            if topdown:
                yield 'dir', path
            for path_ in self.listdir(path):
                path_ = os.path.join(path, path_)
                for res in self.walk(path_, topdown=topdown):
                    yield res
            if not topdown:
                yield 'dir', path

    def cwd(self, path, makedirs=False):
        if self.ftp.pwd().strip('/') == path.strip('/'):
            return
        dirnames = path.strip('/').split('/')
        if path.startswith('/'):
            dirnames.insert(0, '/')

        for dirname in dirnames:
            try:
                self.ftp.cwd(dirname)
            except error_perm, e:
                if not makedirs:
                    raise FtpError(str(e))
                self.ftp.mkd(dirname)
                self.ftp.cwd(dirname)

    def download(self, src, dst):
        path, filename = os.path.split(src)
        self.cwd(path)
        path = os.path.dirname(dst)
        if not os.path.exists(path):
            os.makedirs(path)
        with open(dst, 'w') as fd:
            self.ftp.retrbinary('RETR %s' % filename, fd.write)

    def upload(self, src, dst):
        path, filename = os.path.split(dst)
        self.cwd(path, makedirs=True)
        with open(src) as fd:
            self.ftp.storbinary('STOR %s' % filename, fd)
