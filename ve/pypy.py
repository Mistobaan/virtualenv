from environment import BasePythonDistribution

class PyPyDistribution(BasePythonDistribution):

    def __init__(self, *args, **kwds):
        super(PyPyDistribution, self).__init__(*args, **kwds)
        self._ignore_exec_prefix = True

    def path_locations(self):
        self._lib_dir = home_dir
        self._inc_dir = join(home_dir, 'include')
        self._bin_dir = join(home_dir, 'bin')
        self._stdinc_dir = join(self.prefix(), 'include')

    def copy_executable(self):
        # make a symlink python --> pypy-c
        python_executable = os.path.join(os.path.dirname(py_executable), 'python')
        if sys.platform in ('win32', 'cygwin'):
            python_executable += '.exe'
        logger.info('Also created executable %s' % python_executable)
        copyfile(py_executable, python_executable)

        if sys.platform == 'win32':
            for name in 'libexpat.dll', 'libpypy.dll', 'libpypy-c.dll', 'libeay32.dll', 'ssleay32.dll', 'sqlite.dll':
                src = join(prefix, name)
                if os.path.exists(src):
                    copyfile(src, join(bin_dir, name))
