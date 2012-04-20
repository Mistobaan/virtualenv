import ve
from ve.unix import UnixDistribution
from ve.utils import *

class DarwinDistribution(UnixDistribution):

    def stdlib_dirs(self):
        stdlib_dirs = super(DarwinDistribution, self).stdlib_dirs()
        stdlib_dirs.append(join(stdlib_dirs[0], 'site-packages'))
        return stdlib_dirs

    def py_executable(self):
        py_executable = super(DarwinDistribution, self).py_executable()
        if 'Python.framework' in self.prefix():
            if re.search(r'/Python(?:-32|-64)*$', py_executable):
                # The name of the python executable is not quite what
                # we want, rename it.
                py_executable = os.path.join(
                        os.path.dirname(py_executable), 'python')
        return py_executable

    def platform_specific(self):
        prefix = self.prefix()
        if '.framework' in prefix:
            if 'Python.framework' in prefix:
                logger.debug('MacOSX Python framework detected')
                # Make sure we use the the embedded interpreter inside
                # the framework, even if sys.executable points to
                # the stub executable in ${sys.prefix}/bin
                # See http://groups.google.com/group/python-virtualenv/
                #                              browse_thread/thread/17cab2f85da75951
                original_python = os.path.join(
                    prefix, 'Resources/Python.app/Contents/MacOS/Python')
            if 'EPD' in prefix:
                logger.debug('EPD framework detected')
                original_python = os.path.join(prefix, 'bin/python')
            self._fs.copyfile(original_python, py_executable)

            # Copy the framework's dylib into the virtual
            # environment
            virtual_lib = os.path.join(home_dir, '.Python')

            if os.path.exists(virtual_lib):
                os.unlink(virtual_lib)
            copyfile(
                os.path.join(prefix, 'Python'),
                virtual_lib)

            # And then change the install_name of the copied python executable
            try:
                call_subprocess(
                    ["install_name_tool", "-change",
                     os.path.join(prefix, 'Python'),
                     '@executable_path/../.Python',
                     py_executable])
            except:
                logger.fatal(
                    "Could not call install_name_tool -- you must have Apple's development tools installed")
                raise

            # Some tools depend on pythonX.Y being present
            py_executable_version = '%s.%s' % (
                sys.version_info[0], sys.version_info[1])
            if not py_executable.endswith(py_executable_version):
                # symlinking pythonX.Y > python
                pth = py_executable + '%s.%s' % (
                        sys.version_info[0], sys.version_info[1])
                if os.path.exists(pth):
                    os.unlink(pth)
                os.symlink('python', pth)
            else:
                # reverse symlinking python -> pythonX.Y (with --python)
                pth = join(bin_dir, 'python')
                if os.path.exists(pth):
                    os.unlink(pth)
                os.symlink(os.path.basename(py_executable), pth)
