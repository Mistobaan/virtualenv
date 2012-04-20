import ve
import distutils
from ve.utils import *
from ve.utils import _find_file
from ve.log import logger, Logger

def _filter_ez_setup(line, project_name='setuptools'):
    if not line.strip():
        return Logger.DEBUG
    if project_name == 'distribute':
        for prefix in ('Extracting', 'Now working', 'Installing', 'Before',
                       'Scanning', 'Setuptools', 'Egg', 'Already',
                       'running', 'writing', 'reading', 'installing',
                       'creating', 'copying', 'byte-compiling', 'removing',
                       'Processing'):
            if line.startswith(prefix):
                return Logger.DEBUG
        return Logger.DEBUG
    for prefix in ['Reading ', 'Best match', 'Processing setuptools',
                   'Copying setuptools', 'Adding setuptools',
                   'Installing ', 'Installed ']:
        if line.startswith(prefix):
            return Logger.DEBUG
    return Logger.INFO

def install_distribute(py_executable, unzip=False,
                       search_dirs=None, never_download=False):
    _install_req(py_executable, unzip, distribute=True,
                 search_dirs=search_dirs, never_download=never_download)

_pip_re = re.compile(r'^pip-.*(zip|tar.gz|tar.bz2|tgz|tbz)$', re.I)
def install_pip(py_executable, search_dirs=None, never_download=False):
    if search_dirs is None:
        search_dirs = file_search_dirs()

    filenames = []
    for dir in search_dirs:
        filenames.extend([join(dir, fn) for fn in os.listdir(dir)
                          if _pip_re.search(fn)])
    filenames = [(os.path.basename(filename).lower(), i, filename) for i, filename in enumerate(filenames)]
    filenames.sort()
    filenames = [filename for basename, i, filename in filenames]
    if not filenames:
        filename = 'pip'
    else:
        filename = filenames[-1]
    easy_install_script = 'easy_install'
    if sys.platform == 'win32':
        easy_install_script = 'easy_install-script.py'
    # There's two subtle issues here when invoking easy_install.
    # 1. On unix-like systems the easy_install script can *only* be executed
    #    directly if its full filesystem path is no longer than 78 characters.
    # 2. A work around to [1] is to use the `python path/to/easy_install foo`
    #    pattern, but that breaks if the path contains non-ASCII characters, as
    #    you can't put the file encoding declaration before the shebang line.
    # The solution is to use Python's -x flag to skip the first line of the
    # script (and any ASCII decoding errors that may have occurred in that line)
    cmd = [py_executable, '-x', join(os.path.dirname(py_executable), easy_install_script), filename]
    # jython and pypy don't yet support -x
    if is_jython or is_pypy:
        cmd.remove('-x')
    if filename == 'pip':
        if never_download:
            logger.fatal("Can't find any local distributions of pip to install "
                         "and --never-download is set.  Either re-run virtualenv "
                         "without the --never-download option, or place a pip "
                         "source distribution (zip/tar.gz/tar.bz2) in one of these "
                         "locations: %r" % search_dirs)
            sys.exit(1)
        logger.info('Installing pip from network...')
    else:
        logger.info('Installing existing %s distribution: %s' % (
                os.path.basename(filename), filename))
    logger.start_progress('Installing pip...')
    logger.indent += 2
    def _filter_setup(line):
        return _filter_ez_setup(line, 'pip')
    try:
        call_subprocess(cmd, show_stdout=False,
                        filter_stdout=_filter_setup)
    finally:
        logger.indent -= 2
        logger.end_progress()


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

            executable = self._fs.resolve_link(executable)
            logger.info("Reference Python Executable: %s", executable)
            # For the way CPython's prefix loads we can't use symlinks for the executable
            # http://svn.python.org/projects/python/trunk/Modules/getpath.c
            self._fs.copyfile(executable, py_executable, symlink=False)
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
                
                self._fs.copyfile(sys.executable, secondary_exe, symlink=False)
                self._fs.make_exe(secondary_exe)

        if sys.platform == 'win32' and ' ' in py_executable:
            # There's a bug with subprocess on Windows when using a first
            # argument that has a space in it.  Instead we have to quote
            # the value:
            py_executable = '"%s"' % py_executable

        # NOTE: keep this check as one line, cmd.exe doesn't cope with line breaks
        cmd = [py_executable, '-c', 'import sys;import os;out=sys.stdout;'
            'getattr(out, "buffer", out).write(os.path.abspath(sys.prefix.encode("utf-8")))']
        logger.info('Testing executable with %s %s "%s"' % tuple(cmd))

        proc_stdout = call_subprocess(cmd)[0]

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
        self.fix_local_scheme()

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
        self._py_executable,
        unzip=self._options.unzip_setuptools
        search_dirs=self._options.search_dirs
        never_download=self._options.never_download

        self._install_req(self._py_executable,
                          unzip,
                          search_dirs,
                          never_download=never_download)

    def install_pip(self):
        install_pip(self._py_executable,
                    search_dirs=self._options.search_dirs,
                    never_download=self._options.never_download)

    def install_activate(self):
        home_dir = os.path.abspath(self._home_dir)
        prompt=self._options.prompt
        if sys.platform == 'win32' or is_jython and os._name == 'nt':
            files = {
                'activate.bat': ACTIVATE_BAT,
                'deactivate.bat': DEACTIVATE_BAT,
                'activate.ps1': ACTIVATE_PS,
            }

            # MSYS needs paths of the form /c/path/to/file
            drive, tail = os.path.splitdrive(home_dir.replace(os.sep, '/'))
            home_dir_msys = (drive and "/%s%s" or "%s%s") % (drive[:1], tail)

            # Run-time conditional enables (basic) Cygwin compatibility
            home_dir_sh = ("""$(if [ "$OSTYPE" "==" "cygwin" ]; then cygpath -u '%s'; else echo '%s'; fi;)""" %
                           (home_dir, home_dir_msys))
            files['activate'] = ACTIVATE_SH.replace('__VIRTUAL_ENV__', home_dir_sh)

        else:
            files = {'activate': ACTIVATE_SH}

            # suppling activate.fish in addition to, not instead of, the
            # bash script support.
            files['activate.fish'] = ACTIVATE_FISH

            # same for csh/tcsh support...
            files['activate.csh'] = ACTIVATE_CSH

        files['activate_this.py'] = ACTIVATE_THIS
        if hasattr(home_dir, 'decode'):
            home_dir = home_dir.decode(sys.getfilesystemencoding())
        vname = os.path.basename(home_dir)
        for name, content in files.items():
            content = content.replace('__VIRTUAL_PROMPT__', prompt or '')
            content = content.replace('__VIRTUAL_WINPROMPT__', prompt or '(%s)' % vname)
            content = content.replace('__VIRTUAL_ENV__', home_dir)
            content = content.replace('__VIRTUAL_NAME__', vname)
            content = content.replace('__BIN_NAME__', os.path.basename(self._bin_dir))
            self._fs.writefile(os.path.join(self._bin_dir, name), content)

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

    def _install_req(self, py_executable, unzip=False, distribute=False,
                     search_dirs=None, never_download=False):

        if search_dirs is None:
            search_dirs = file_search_dirs()

        if not distribute:
            setup_fn = 'setuptools-0.6c11-py%s.egg' % sys.version[:3]
            project_name = 'setuptools'
            bootstrap_script = EZ_SETUP_PY
            source = None
        else:
            setup_fn = None
            source = 'distribute-0.6.24.tar.gz'
            project_name = 'distribute'
            bootstrap_script = DISTRIBUTE_SETUP_PY

        if setup_fn is not None:
            setup_fn = _find_file(setup_fn, search_dirs)

        if source is not None:
            source = _find_file(source, search_dirs)

        if is_jython and os._name == 'nt':
            # Jython's .bat sys.executable can't handle a command line
            # argument with newlines
            fd, ez_setup = tempfile.mkstemp('.py')
            os.write(fd, bootstrap_script)
            os.close(fd)
            cmd = [py_executable, ez_setup]
        else:
            cmd = [py_executable, '-c', bootstrap_script]
        if unzip:
            cmd.append('--always-unzip')
        env = {}
        remove_from_env = []
        if logger.stdout_level_matches(logger.DEBUG):
            cmd.append('-v')

        old_chdir = os.getcwd()
        if setup_fn is not None and os.path.exists(setup_fn):
            logger.info('Using existing %s egg: %s' % (project_name, setup_fn))
            cmd.append(setup_fn)
            if os.environ.get('PYTHONPATH'):
                env['PYTHONPATH'] = setup_fn + os.path.pathsep + os.environ['PYTHONPATH']
            else:
                env['PYTHONPATH'] = setup_fn
        else:
            # the source is found, let's chdir
            if source is not None and os.path.exists(source):
                logger.info('Using existing %s egg: %s' % (project_name, source))
                os.chdir(os.path.dirname(source))
                # in this case, we want to be sure that PYTHONPATH is unset (not
                # just empty, really unset), else CPython tries to import the
                # site.py that it's in virtualenv_support
                remove_from_env.append('PYTHONPATH')
            else:
                if never_download:
                    logger.fatal("Can't find any local distributions of %s to install "
                                 "and --never-download is set.  Either re-run virtualenv "
                                 "without the --never-download option, or place a %s "
                                 "distribution (%s) in one of these "
                                 "locations: %r" % (project_name, project_name,
                                                    setup_fn or source,
                                                    search_dirs))
                    sys.exit(1)

                logger.info('No %s egg found; downloading' % project_name)
            cmd.extend(['--always-copy', '-U', project_name])
        logger.start_progress('Installing %s...' % project_name)
        logger.indent += 2
        cwd = None
        if project_name == 'distribute':
            env['DONT_PATCH_SETUPTOOLS'] = 'true'

        if not os.access(os.getcwd(), os.W_OK):
            cwd = tempfile.mkdtemp()
            if source is not None and os.path.exists(source):
                # the current working dir is hostile, let's copy the
                # tarball to a temp dir
                target = os.path.join(cwd, os.path.split(source)[-1])
                shutil.copy(source, target)
        try:
            call_subprocess(cmd, show_stdout=False,
                            filter_stdout=_filter_ez_setup,
                            extra_env=env,
                            remove_from_env=remove_from_env,
                            cwd=cwd)
        finally:
            logger.indent -= 2
            logger.end_progress()
            if os.getcwd() != old_chdir:
                os.chdir(old_chdir)
            if is_jython and os._name == 'nt':
                os.remove(ez_setup)

    def install_distutils(self):
        distutils_path = change_prefix(distutils.__path__[0], self._home_dir)
        self._fs.mkdir(distutils_path)
        ## FIXME: maybe this prefix setting should only be put in place if
        ## there's a local distutils.cfg with a prefix setting?
        ## FIXME: this is breaking things, removing for now:
        #home_dir = os.path.abspath(self._home_dir)
        #distutils_cfg = DISTUTILS_CFG + "\n[install]\nprefix=%s\n" % home_dir
        self._fs.writefile(join(distutils_path, '__init__.py'), DISTUTILS_INIT)
        self._fs.writefile(join(distutils_path, 'distutils.cfg'), DISTUTILS_CFG, overwrite=False)
