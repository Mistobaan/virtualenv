from ve.utils import *
from ve.log import logger
import ve
import distutils


class BasePythonDistribution(object):

    def __init__(self, fs, home_dir, options):
        self._home_dir = home_dir
        self._fs = fs
        self._options = options
        self._ignore_exec_prefix = False

    def path_locations(self):
        raise NotImplementedError

    def py_executable(self):
        return join(self._bin_dir, os.path.basename(sys.executable))

    def create(self):
        """
        If ``site_packages`` is true, then the global ``site-packages/``
        directory will be on the path.
    
        If ``clear`` is true (default False) then the environment will
        first be cleared.
        """
        # home_dir, lib_dir, inc_dir, bin_dir = path_locations(home_dir)
        self.path_locations()

        self.clear()

        res = self.install_python()

        self._py_executable = os.path.abspath(res)

        self.install_distutils()
        if self.should_install_distribute():
            self.install_distribute()
        else:
            self.install_setuptools()
        self.install_pip()
        self.install_activate()

    def clear(self):
        self._fs.rmtree(self._lib_dir)
        ## FIXME: why not delete it?
        ## Maybe it should delete everything with #!/path/to/venv/python in it
        logger.notify('Not deleting %s', self._bin_dir)

    def list_required_lib_files(self, stdlib_dirs):
        file_list = []
        for stdlib_dir in stdlib_dirs:
            if not os.path.isdir(stdlib_dir):
                continue
            for fn in os.listdir(stdlib_dir):
                bn = os.path.splitext(fn)[0]
                if fn != 'site-packages' and bn in ve.REQUIRED_FILES:
                    source = join(stdlib_dir, fn)
                    dest = join(self._lib_dir, fn)
                    file_list.append((source, dest))
        return file_list

    def copy_site_packages(self):
        home_dir = self._home_dir
        self._fs.mkdir(join(self._lib_dir, 'site-packages'))
        import site
        site_filename = site.__file__
        if site_filename.endswith('.pyc'):
            site_filename = site_filename[:-1]
        elif site_filename.endswith('$py.class'):
            site_filename = site_filename.replace('$py.class', '.py')
        site_filename_dst = change_prefix(site_filename, home_dir)
        site_dir = os.path.dirname(site_filename_dst)
        self._fs.writefile(site_filename_dst, ve.SITE_PY)
        self._fs.writefile(join(site_dir, 'orig-prefix.txt'), self.prefix())
        site_packages_filename = join(site_dir, 'no-global-site-packages.txt')
        if not self._options.system_site_packages:
            self._fs.writefile(site_packages_filename, '')
        else:
            if os.path.exists(site_packages_filename):
                logger.info('Deleting %s' % site_packages_filename)
                os.unlink(site_packages_filename)

    def prefix(self):
        if hasattr(sys, 'real_prefix'):
            logger.notify('Using real prefix %r' % sys.real_prefix)
            prefix = sys.real_prefix
        else:
            prefix = sys.prefix
        return prefix

    def copy_stdinc(self):
        if os.path.exists(self._stdinc_dir):
            self._fs.copyfile(self._stdinc_dir, self._inc_dir)
        else:
            logger.debug('No include dir %s' % self._stdinc_dir)

    def copy_executable(self):
        pass

    def install_python(self):
        """Install just the base environment, no distutils patches etc"""
        home_dir = self._home_dir
        lib_dir = self._lib_dir
        inc_dir = self._inc_dir
        bin_dir = self._bin_dir
        prefix = self.prefix()

        if sys.executable.startswith(bin_dir):
            print('Please use the *system* python to run this script')
            return

        self._fs.mkdir(self._lib_dir)
        self.fix_lib64()

        stdlib_dirs = self.stdlib_dirs()
        if hasattr(os, 'symlink'):
            logger.info('Symlinking Python bootstrap modules')
        else:
            logger.info('Copying Python bootstrap modules')
        logger.indent += 2
        try:
            for src, dest in self.list_required_lib_files(stdlib_dirs):
                self._fs.copyfile(src, dest)
            self.copy_required_modules()
        finally:
            logger.indent -= 2

        self.copy_site_packages()
        self.copy_stdinc()

        # pypy never uses exec_prefix, just ignore it
        if not self._ignore_exec_prefix:
            if sys.exec_prefix != self.prefix():
                for fn in os.listdir(self._exec_dir):
                    self._fs.copyfile(join(self._exec_dir, fn),
                                      join(self._lib_dir, fn))

        self.platform_specific()

        # Bin exec
        self._fs.mkdir(bin_dir)
        py_executable = self.py_executable()

        logger.notify('New %s executable in %s', expected_exe, py_executable)
        pcbuild_dir = os.path.dirname(sys.executable)
        pyd_pth = os.path.join(lib_dir, 'site-packages', 'virtualenv_builddir_pyd.pth')

        if is_win and os.path.exists(os.path.join(pcbuild_dir, 'build.bat')):
            logger.notify('Detected python running from build directory %s', pcbuild_dir)
            logger.notify('Writing .pth file linking to build directory for *.pyd files')
            self._fs.writefile(pyd_pth, pcbuild_dir)
        else:
            pcbuild_dir = None
            if os.path.exists(pyd_pth):
                logger.info('Deleting %s (not Windows env or not build directory python)' % pyd_pth)
                os.unlink(pyd_pth)

        if sys.executable != py_executable:
            ## FIXME: could I just hard link?
            executable = sys.executable
            if sys.platform == 'cygwin' and os.path.exists(executable + '.exe'):
                # Cygwin misreports sys.executable sometimes
                executable += '.exe'
                py_executable += '.exe'
                logger.info('Executable actually exists in %s' % executable)
            self._fs.copyfile(executable, py_executable)
            self._fs.make_exe(py_executable)

            self.copy_executable()

        if os.path.splitext(os.path.basename(py_executable))[0] != expected_exe:
            secondary_exe = os.path.join(os.path.dirname(py_executable),
                                         expected_exe)
            py_executable_ext = os.path.splitext(py_executable)[1]
            if py_executable_ext == '.exe':
                # python2.4 gives an extension of '.4' :P
                secondary_exe += py_executable_ext
            if os.path.exists(secondary_exe):
                logger.warn('Not overwriting existing %s script %s (you must use %s)'
                            % (expected_exe, secondary_exe, py_executable))
            else:
                logger.notify('Also creating executable in %s' % secondary_exe)
                self._fs.copyfile(sys.executable, secondary_exe)
                make_exe(secondary_exe)

        if sys.platform == 'win32' and ' ' in py_executable:
            # There's a bug with subprocess on Windows when using a first
            # argument that has a space in it.  Instead we have to quote
            # the value:
            py_executable = '"%s"' % py_executable

        # NOTE: keep this check as one line, cmd.exe doesn't cope with line breaks
        cmd = [py_executable, '-c', 'import sys;out=sys.stdout;'
            'getattr(out, "buffer", out).write(sys.prefix.encode("utf-8"))']
        logger.info('Testing executable with %s %s "%s"' % tuple(cmd))
        try:
            proc = subprocess.Popen(cmd,
                                stdout=subprocess.PIPE)
            proc_stdout, proc_stderr = proc.communicate()
        except OSError:
            e = sys.exc_info()[1]
            if e.errno == errno.EACCES:
                logger.fatal('ERROR: The executable %s could not be run: %s' % (py_executable, e))
                sys.exit(100)
            else:
              raise e

        proc_stdout = proc_stdout.strip().decode("utf-8")
        proc_stdout = os.path.normcase(os.path.abspath(proc_stdout))
        norm_home_dir = os.path.normcase(os.path.abspath(home_dir))
        if hasattr(norm_home_dir, 'decode'):
            norm_home_dir = norm_home_dir.decode(sys.getfilesystemencoding())
        if proc_stdout != norm_home_dir:
            logger.fatal(
                'ERROR: The executable %s is not functioning' % py_executable)
            logger.fatal(
                'ERROR: It thinks sys.prefix is %r (should be %r)'
                % (proc_stdout, norm_home_dir))
            logger.fatal(
                'ERROR: virtualenv is not compatible with this system or executable')
            if sys.platform == 'win32':
                logger.fatal(
                    'Note: some Windows users have reported this error when they '
                    'installed Python for "Only this user" or have multiple '
                    'versions of Python installed. Copying the appropriate '
                    'PythonXX.dll to the virtualenv Scripts/ directory may fix '
                    'this problem.')
            sys.exit(100)
        else:
            logger.info('Got sys.prefix result: %r' % proc_stdout)

        pydistutils = os.path.expanduser('~/.pydistutils.cfg')
        if os.path.exists(pydistutils):
            logger.notify('Please make sure you remove any previous custom paths from '
                          'your %s file.' % pydistutils)
        ## FIXME: really this should be calculated earlier

        fix_local_scheme(home_dir)

        return py_executable

    def install_distutils(self):
        install_distutils(self._home_dir)

    def should_install_distribute(self):
        # use_distribute also is True if VIRTUALENV_DISTRIBUTE env var is set
        # we also check VIRTUALENV_USE_DISTRIBUTE for backwards compatibility
        return self._options.use_distribute or os.environ.get('VIRTUALENV_USE_DISTRIBUTE')

    def install_distribute(self):
        install_distribute(self._py_executable, unzip=self._options.unzip_setuptools,
                           search_dirs=self._options.search_dirs,
                           never_download=self._options.never_download)

    def install_setuptools(self):
        install_setuptools(self._py_executable, unzip=self._options.unzip_setuptools,
                           search_dirs=self._options.search_dirs,
                           never_download=self._options.never_download)

    def install_pip(self):
        install_pip(self._py_executable,
                    search_dirs=self._options.search_dirs,
                    never_download=self._options.never_download)

    def install_activate(self):
        install_activate(self._home_dir, self._bin_dir, self._options.prompt)

    def platform_specific(self):
        pass

    def fix_local_scheme(self):
        """
        Platforms that use the "posix_local" install scheme (like Ubuntu with
        Python 2.7) need to be given an additional "local" location, sigh.
        """
        home_dir = self._home_dir
        try:
            import sysconfig
        except ImportError:
            pass
        else:
            if sysconfig._get_default_scheme() == 'posix_local':
                local_path = os.path.join(home_dir, 'local')
                if not os.path.exists(local_path):
                    self._fs.mkdir(local_path)
                    for subdir_name in os.listdir(home_dir):
                        if subdir_name == 'local':
                            continue
                        src = os.path.abspath(os.path.join(home_dir, subdir_name))
                        dst = os.path.join(local_path, subdir_name)
                        self._fs.mklink(src,dst)

    def fix_lib64(self):
        """
        Some platforms (particularly Gentoo on x64) put things in lib64/pythonX.Y
        instead of lib/pythonX.Y.  If this is such a platform we'll just create a
        symlink so lib64 points to lib
        """
        if [p for p in distutils.sysconfig.get_config_vars().values()
            if isinstance(p, basestring) and 'lib64' in p]:
            logger.debug('This system uses lib64; symlinking lib64 to lib')
            assert os.path.basename(self._lib_dir) == 'python%s' % sys.version[:3], (
                "Unexpected python lib dir: %r" % self._lib_dir)
            lib_parent = os.path.dirname(self._lib_dir)
            assert os.path.basename(lib_parent) == 'lib', (
                "Unexpected parent dir: %r" % lib_parent)

            target = os.path.join(os.path.dirname(lib_parent), 'lib64')
            self._fs.copyfile(lib_parent, target)

    def copy_required_modules(self):
        import imp
        # If we are running under -p, we need to remove the current
        # directory from sys.path temporarily here, so that we
        # definitely get the modules from the site directory of
        # the interpreter we are running under, not the one
        # virtualenv.py is installed under (which might lead to py2/py3
        # incompatibility issues)
        dst_prefix = self._home_dir
        _prev_sys_path = sys.path
        if os.environ.get('VIRTUALENV_INTERPRETER_RUNNING'):
            sys.path = sys.path[1:]
        try:
            for modname in ve.REQUIRED_MODULES:
                if modname in sys.builtin_module_names:
                    logger.info("Ignoring built-in bootstrap module: %s" % modname)
                    continue
                try:
                    f, filename, _ = imp.find_module(modname)
                except ImportError:
                    logger.info("Cannot import bootstrap module: %s" % modname)
                else:
                    if f is not None:
                        f.close()
                    dst_filename = change_prefix(filename, dst_prefix)
                    self._fs.copyfile(filename, dst_filename)
                    if filename.endswith('.pyc'):
                        pyfile = filename[:-1]
                        if os.path.exists(pyfile):
                            self._fs.copyfile(pyfile, dst_filename[:-1])
        finally:
            sys.path = _prev_sys_path
