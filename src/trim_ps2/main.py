#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  This file is part of "trim-ps2" project
#
#  Author: Roman Gladyshev <remicollab@gmail.com>
#  License: BSD 3-Clause "New" or "Revised" License
#
#  SPDX-License-Identifier: BSD-3-Clause
#  License text is available in the LICENSE file and online:
#  http://www.opensource.org/licenses/BSD-3-Clause
#
#  Copyright (c) 2020, remico

"""Analyses what the PySide2 modules a python package depends on, then remove all unused modules.
Intended to use in conjunction with Briefcase tool.
"""

import subprocess
import sys

from os import getcwd
from pathlib import Path

E_CODE_NO_TARGET = 1
E_CODE_TARGET_ABORT = 2
E_CODE_NO_PS2 = 3


def app_module():
    try:
        target = sys.argv[1]
        return target
    except IndexError:
        print(f"Usage: python3 -m {__package__} <PYTHON_PACKAGE> [-d] [--dump]")
        sys.exit(E_CODE_NO_TARGET)


def check_option(o: str):
    exists = o in sys.argv
    if exists:
        sys.argv.remove(o)
    return exists


DUMP = check_option("--dump")  # dump all required dependencies

# FIXME
# if check_option("-d"):
#     command = f"{sys.executable} -m pudb {__file__} {app_module()}"
#     res = pexpect.interact(...),
#     sys.exit(res.returncode)


def run_p(cmd, errors=False):
    return subprocess.run(cmd, cwd=working_dir, text=True, shell=True,
                          stderr=subprocess.STDOUT if errors else subprocess.PIPE,
                          stdout=subprocess.PIPE)


def locate_ps2(root_path):
    ps2_dir = root_path / 'PySide2/'
    if not ps2_dir.exists():
        command = fr"{sys.executable} -B -v -c 'import PySide2.QtCore' 2>&1 | grep 'loaded' | grep -oP '/.*QtCore.*\.so'"
        res = run_p(command, errors=True)

        if not res.stdout:
            print(f"ERROR: PySide2 not found")
            sys.exit(E_CODE_NO_PS2)

        ps2_dir = Path(res.stdout).parent
    return ps2_dir


def locate_cwd(root_path):
    app_dir = root_path / "app"
    return str(app_dir) if app_dir.exists() else getcwd()


app_bundle_path = Path(sys.executable).parent.parent
app_bundle_packages_path = app_bundle_path / "app_packages"
working_dir = locate_cwd(app_bundle_path)
ps2_path = locate_ps2(app_bundle_packages_path)


def find_app_deps(py_module):
    error_msgs = [
        'Abort',
        'ImportError',
        'Traceback',
    ]
    errors_filter = '|'.join(error_msgs)
    libs_filer = r"/.*\.so[\.\d]*"
    libs_import_error_filter = r"(?<=ImportError: ).*.so[\.\d]*"

    command = f"QT_DEBUG_PLUGINS=1 {sys.executable} -B -v -m {py_module} 2>&1"
    output_filter = f' | egrep "loaded|{errors_filter}" | grep -oP "{libs_filer}|{libs_import_error_filter}|{errors_filter}"'

    res = run_p(command + output_filter, errors=True)

    if (any(emsg in res.stdout for emsg in error_msgs) and not DUMP) or res.returncode != 0:
        output_filter = " | egrep -v '# cleanup|# destroy'"
        res = run_p(command + output_filter, errors=True)
        print(res.stdout)
        print(f"\nERROR: '{py_module}' module exited with code {res.returncode}. Abort deps gathering.")
        sys.exit(E_CODE_TARGET_ABORT)

    all_deps = res.stdout.splitlines()
    so_libs = {lib for lib in all_deps if ".so" in lib and "python" not in Path(lib).name}

    return so_libs


def is_path(value: str):
    return len(value.split('/')) > 1


def find_all_elf_deps(libs):
    deps = set()

    for lib in libs:
        deps.add(lib)

        if not is_path(lib):  # don't even try to resolve plain names
            continue

        loaded_path = r"(?<==>).*(?=\()"
        not_found_name = r".*(?==> not found)"
        res = run_p(f"ldd {lib} | egrep -v 'linux-vdso|ld-linux' | grep -oP '{loaded_path}|{not_found_name}'")
        lines = res.stdout.splitlines()
        s = {ln.strip() for ln in lines}
        deps.update(s)

    return deps


def dpkg_resolve(libs):
    resolved_paths = set()
    unresolved_names_and_paths = set()

    for lib_path in libs:
        res = run_p(f"dpkg -S '{lib_path}'")
        if not res.stdout.strip() \
                or "no path found" in res.stdout:
            unresolved_names_and_paths.add(lib_path)
        elif res.stdout.strip():
            resolved_paths.add(res.stdout.split(':')[0])
        else:
            print(f"@ WARNING: something wrong with '{lib_path}'")

    return resolved_paths, unresolved_names_and_paths


def handle_dpkg_unresolved(libs):
    if libs:
        lib_paths = '\n'.join(libs)
        res = run_p(f"echo '{lib_paths}' | apt-file find -f -", errors=True)

        packages = {lib: set() for lib in libs}  # initialize

        for pkg in res.stdout.splitlines():
            pkg_name = pkg.split(": ")[0]
            lib_suggested_name = pkg.split(": ")[1]

            def resolve_lib_name(name):
                for lib in libs:
                    if lib in name:
                        return lib
                return "#"

            lib_name = resolve_lib_name(lib_suggested_name)
            packages[lib_name].add(pkg_name)

        print()
        print("@ apt-file suggests:\n")
        for k, v in packages.items():
            print(f"> {Path(k).name:20}: {list(v)}")


def filter_python_modules(libs):
    modules = set()

    names = {lib for lib in libs if not is_path(lib)}  # plain .so names
    paths = {lib for lib in libs if is_path(lib)}  # .so paths

    for path in paths:
        if "lib/python" in path:
            modules.add(path)
        elif str(app_bundle_packages_path) in path:
            modules.add(path)

        for name in names:
            if name in path:
                modules.add(name)

    return modules


def to_names(paths):
    return {Path(path).name for path in paths}


def calculate_pyside2_size():
    return run_p(f"du -sh {ps2_path}").stdout.split('\t')[0]


def main():
    required_deps = set()

    print("\n***************** APP DEPS *******************\n")
    app_deps = find_app_deps(app_module())
    print(to_names(app_deps))

    print("\n************** RECURSIVE DEPS ****************\n")
    all_deps = find_all_elf_deps(app_deps)

    ps2_modules = {m for m in all_deps if 'PySide2' in m}
    required_deps.update(ps2_modules)
    other_libs = all_deps - ps2_modules

    if DUMP:
        print("@ PySide2 modules:")
        print(to_names(ps2_modules))
        print()
        print("@ other deps:")
        print(to_names(other_libs))

        print()
        print("Resolving dependencies...")

        resolved, unresolved = dpkg_resolve(other_libs)

        if resolved:
            print()
            print("@ dpkg resolved packages:")
            print("$ sudo apt install", ' '.join(resolved))

        # filter other (non-PS2) python modules
        other_python_modules = filter_python_modules(unresolved)
        unresolved -= other_python_modules

        print()
        print("@ recognized as python modules:")
        print(to_names(other_python_modules))

        print()
        print("@ total unresolved:")
        print(to_names(unresolved))

        # find remaining dependencies in OS index
        handle_dpkg_unresolved(unresolved)

    print("\n********** REQUIRED PySide2 ELFs **********\n")
    print(to_names(required_deps))

    if not DUMP:
        print()
        print("Clearing unused dependencies...")

        size_before = calculate_pyside2_size()

        globbed_so = ps2_path.glob("**/*.so*")
        so_paths = [str(so) for so in globbed_so]

        for so_path in so_paths:
            # skip required deps
            if any(Path(so_path).name in dep_path for dep_path in required_deps):
                continue

            run_p(f"rm {so_path}")

        for name in ["designer", "rcc", "uic", "pyside2-lupdate"]:
            run_p(f"find {ps2_path} -type f -name {name} -exec rm {{}} +")

        print("Done")
        print()

        size_after = calculate_pyside2_size()
        print("PySide2 directory size before:", size_before)
        print("PySide2 directory size after:", size_after)
        print()


if __name__ == '__main__':
    main()
