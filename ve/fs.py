import os
import shutil

from ve import *
from ve.log import logger


class FileSystemService(object):

    def mkdir(self, path):
        if not os.path.exists(path):
            logger.info('Creating %s', path)
            os.makedirs(path)
        else:
            logger.info('Directory %s already exists', path)
    def mklink(self, src, dst):
        os.symlink(src,dst)
    
    def rmtree(self, *args):
        rmtree(*args)

    def copytree(self, *args):
        shutil.copytree(*args)

    def copyfile(self, src, dest, **kwds):
        copyfile(src, dest, **kwds)

    def copyfileordir(self, src, dest):
        if os.path.isdir(src):
            shutil.copytree(src, dest, True)
        else:
            shutil.copy2(src, dest)

    def copyfile(self, src, dest, symlink=True):
        if not os.path.exists(src):
            # Some bad symlink in the src
            logger.warn('Cannot find file %s (bad symlink)', src)
            return
        if os.path.exists(dest):
            logger.debug('File %s already exists', dest)
            return
        if not os.path.exists(os.path.dirname(dest)):
            logger.info('Creating parent directories for %s' % os.path.dirname(dest))
            os.makedirs(os.path.dirname(dest))
        if not os.path.islink(src):
            srcpath = os.path.abspath(src)
        else:
            srcpath = os.readlink(src)
        if symlink and hasattr(os, 'symlink') and not is_win:
            logger.info('Symlinking %s', dest)
            try:
                os.symlink(srcpath, dest)
            except (OSError, NotImplementedError):
                logger.info('Symlinking failed, copying to %s', dest)
                self.copyfileordir(src, dest)
        else:
            logger.info('Copying to %s', dest)
            self.copyfileordir(src, dest)

    def writefile(self, dest, content, overwrite=True):
        if not os.path.exists(dest):
            logger.info('Writing %s', dest)
            f = open(dest, 'wb')
            f.write(content.encode('utf-8'))
            f.close()
            return
        else:
            f = open(dest, 'rb')
            c = f.read()
            f.close()
            if c != content.encode("utf-8"):
                if not overwrite:
                    logger.notify('File %s exists with different content; not overwriting', dest)
                    return
                logger.notify('Overwriting %s with new content', dest)
                f = open(dest, 'wb')
                f.write(content.encode('utf-8'))
                f.close()
            else:
                logger.info('Content %s already in place', dest)

    def rmtree(self, dir):
        if os.path.exists(dir):
            logger.notify('Deleting tree %s', dir)
            shutil.rmtree(dir)
        else:
            logger.info('Do not need to delete %s; already gone', dir)

    def make_exe(self, fn):
        if hasattr(os, 'chmod'):
            oldmode = os.stat(fn).st_mode & 0xFFF # 0o7777
            newmode = (oldmode | 0x16D) & 0xFFF # 0o555, 0o7777
            os.chmod(fn, newmode)
            logger.info('Changed mode of %s to %s', fn, oct(newmode))
