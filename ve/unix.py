from environment import BasePythonDistribution
from ve.utils import *
from ve import *


class UnixDistribution(BasePythonDistribution):

    def path_locations(self):
        self._lib_dir = join(self._home_dir, 'lib', py_version)
        self._inc_dir = join(self._home_dir, 'include', py_version + abiflags)
        self._bin_dir = join(self._home_dir, 'bin')
        self._stdinc_dir = join(self.prefix(), 'include', py_version + abiflags)
        self._exec_dir = join(sys.exec_prefix, 'lib', py_version)

    def stdlib_dirs(self):
        stdlib_dirs = [os.path.dirname(os.__file__)]
        return stdlib_dirs
