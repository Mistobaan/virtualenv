import os
import sys
from ve import *
from ve.log import logger


join = os.path.join

def _find_file(filename, dirs):
    for dir in reversed(dirs):
        if os.path.exists(join(dir, filename)):
            return join(dir, filename)
    return filename


def change_prefix(filename, dst_prefix):
    prefixes = [sys.prefix]

    if sys.platform == "darwin":
        prefixes.extend((
            join("/Library/Python", sys.version[:3], "site-packages"),
            join(sys.prefix, "Extras", "lib", "python"),
            join("~", "Library", "Python", sys.version[:3], "site-packages")))

    if hasattr(sys, 'real_prefix'):
        prefixes.append(sys.real_prefix)
    prefixes = [os.path.abspath(p) for p in prefixes]
    filename = os.path.abspath(filename)
    for src_prefix in prefixes:
        if filename.startswith(src_prefix):
            _, relpath = filename.split(src_prefix, 1)
            assert relpath[0] == os.sep
            relpath = relpath[1:]
            return join(dst_prefix, relpath)
    assert False, "Filename %s does not start with any of these prefixes: %s" % \
        (filename, prefixes)


def call_subprocess(cmd, show_stdout=True,
                    filter_stdout=None, cwd=None,
                    raise_on_returncode=True, extra_env=None,
                    remove_from_env=None,
                    capture_stdout=True):
    cmd_parts = []
    for part in cmd:
        if len(part) > 45:
            part = part[:20] + "..." + part[-20:]
        if ' ' in part or '\n' in part or '"' in part or "'" in part:
            part = '"%s"' % part.replace('"', '\\"')
        if hasattr(part, 'decode'):
            try:
                part = part.decode(sys.getdefaultencoding())
            except UnicodeDecodeError:
                part = part.decode(sys.getfilesystemencoding())
        cmd_parts.append(part)
    cmd_desc = ' '.join(cmd_parts)
    if capture_stdout:
        stdout = subprocess.PIPE

    logger.debug("Running command %s" % cmd_desc)
    if extra_env or remove_from_env:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        if remove_from_env:
            for varname in remove_from_env:
                env.pop(varname, None)
    else:
        env = None
    try:
        proc = subprocess.Popen(
            cmd, stderr=subprocess.STDOUT, stdin=None, stdout=stdout,
            cwd=cwd, env=env)
    except Exception:
        e = sys.exc_info()[1]

        if e.errno == errno.EACCES:
            logger.fatal('ERROR: The executable %s could not be run: %s' % (py_executable, e))
            sys.exit(100)
        else:
            logger.fatal("Error %s while executing command %s" % (e, cmd_desc))
            raise e

    all_output = []
    if capture_stdout is not None:
        stdout = proc.stdout
        encoding = sys.getdefaultencoding()
        fs_encoding = sys.getfilesystemencoding()
        while True:
            line = stdout.readline()
            try:
                line = line.decode(encoding)
            except UnicodeDecodeError:
                line = line.decode(fs_encoding)
            if not line:
                break
            line = line.rstrip()
            all_output.append(line)
            if filter_stdout:
                level = filter_stdout(line)
                if isinstance(level, tuple):
                    level, line = level
                logger.log(level, line)
                if not logger.stdout_level_matches(level):
                    logger.show_progress()
            else:
                logger.info(line)
    else:
        proc.communicate()
    proc.wait()
    if proc.returncode:
        if raise_on_returncode:
            if all_output:
                logger.notify('Complete output from command %s:' % cmd_desc)
                logger.notify('\n'.join(all_output) + '\n----------------------------------------')
            raise OSError(
                "Command %s failed with error code %s"
                % (cmd_desc, proc.returncode))
        else:
            logger.warn(
                "Command %s had error code %s"
                % (cmd_desc, proc.returncode))
    return all_output

def file_search_dirs():
    here = os.path.dirname(os.path.abspath(__file__))
    dirs = ['.', here,
            join(here, 'virtualenv_support')]
    if os.path.splitext(os.path.dirname(__file__))[0] != 'virtualenv':
        # Probably some boot script; just in case virtualenv is installed...
        try:
            import virtualenv
        except ImportError:
            pass
        else:
            dirs.append(os.path.join(os.path.dirname(virtualenv.__file__), 'virtualenv_support'))
    return [d for d in dirs if os.path.isdir(d)]
