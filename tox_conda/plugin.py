import json
import logging
import os
import sys

import pluggy

hookimpl = pluggy.HookimplMarker("tox")
log = logging.getLogger("conda")

on_win = bool(sys.platform == "win32")


@hookimpl
def tox_testenv_create(venv, action):
    """Perform creation action for this venv."""
    deps = venv.envconfig.deps
    conda_deps, pip_deps = split_conda_deps(deps)
    venv.envconfig.deps = pip_deps
    venv.envconfig.conda_deps = conda_deps

    # if venv.envconfig.recreate:

    basepython = venv.envconfig.basepython
    if not basepython.startswith("python"):
        raise RuntimeError("The conda plugin only supports python basepython.")
    python_version = basepython[6:]
    env_location = str(venv.path)
    args = [
        "%s" % os.environ["CONDA_EXE"],
        "install",
        "--mkdir",
        "-y",
        "-p",
        env_location,
        "python=%s" % python_version,
    ]
    args.extend(str(dep) for dep in conda_deps)

    env = venv._getenv(testcommand=False)
    redirect = venv.session.config.option.verbose_level < 2

    result = action.popen(args, env=env, redirect=redirect)

    return True if result is None else result


def split_conda_deps(deps):
    """Split dependencies between conda and pip."""
    conda_deps = []
    pip_deps = []
    for dep in deps:
        dep_str = str(dep)
        if dep_str.startswith(("-r", "-e", "-c", ":")):
            pip_deps.append(dep)
        elif dep_str.startswith("--pip"):
            dep.name = dep_str[5:].strip()
            pip_deps.append(dep)
        else:
            conda_deps.append(dep)
    return conda_deps, pip_deps


@hookimpl
def tox_runtest_pre(venv):
    env_var_map = get_activated_env_vars(venv)
    os.environ.clear()
    os.environ.update(env_var_map)


def get_activated_env_vars(venv):
    env_location = str(venv.path)
    cmd_builder = []
    conda = None
    if on_win:
        exes = ["conda.exe", "conda.bat"]
        for exe in exes:
            if is_on_path(exe):
                conda = exe
                cmd_builder += [
                    'CALL "{0}" activate "{1}"'.format(conda, env_location),
                    "&&",
                    '%CONDA_PYTHON_EXE% -c "import os, json; print(json.dumps(dict(os.environ)))"',
                ]
                break
    else:
        exes = ["conda"]
        for exe in exes:
            if is_on_path(exe):
                conda = exe
                cmd_builder += [
                    "sh -c '" 'eval "$("{0}" shell.posix hook)"'.format(conda),
                    "&&",
                    "conda activate {0}".format(env_location),
                    "&&",
                    '"$CONDA_PYTHON_EXE" -c "import os, json; print(json.dumps(dict(os.environ)))"',
                    "'",
                ]
    if not conda:
        raise RuntimeError("Unable to find conda on path.")

    cmd = " ".join(cmd_builder)
    env = venv._getenv(testcommand=False)
    action = venv.session.newaction(venv, "activate")
    with action:
        result = action.popen(
            [cmd], env=env, redirect=False, returnout=True, shell=True
        )
    env_var_map = json.loads(result)
    return env_var_map


def is_on_path(cmd):
    """Check whether a command or executable is on path."""
    return any(
        os.access(os.path.join(path, cmd), os.X_OK)
        for path in os.environ["PATH"].split(os.pathsep)
    )
