from environment import BasePythonDistribution


class JythonDistribution(BasePythonDistribution):

    def path_locations(self):
        self._lib_dir = join(self._home_dir, 'Lib')
        self._inc_dir = join(self._home_dir, 'Include')
        self._bin_dir = join(self._home_dir, 'bin')
        self._exec_dir = join(sys.exec_prefix, 'Lib')

    def platform_specific(self):
        if is_jython:
            prefix = self.prefix()
            # Jython has either jython-dev.jar and javalib/ dir, or just
            # jython.jar
            for name in 'jython-dev.jar', 'javalib', 'jython.jar':
                src = join(prefix, name)
                if os.path.exists(src):
                    self._fs.copyfile(src, join(home_dir, name))
            # XXX: registry should always exist after Jython 2.5rc1
            src = join(prefix, 'registry')
            if os.path.exists(src):
                self._fs.copyfile(src, join(home_dir, 'registry'), symlink=False)
            self._fs.copyfile(join(prefix, 'cachedir'), join(home_dir, 'cachedir'),
                     symlink=False)
