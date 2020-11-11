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

from pathlib import Path


E_CODE_NO_TARGET = 1
E_CODE_TARGET_ABORT = 2
E_CODE_NO_PS2 = 3

try:
    app_module = sys.argv[1]
except IndexError:
    print(f"Usage: python3 -m {__package__} <PYTHON_PACKAGE>")
    sys.exit(E_CODE_NO_TARGET)


app_bundle_path = Path(sys.executable).parent.parent
ps2_path = app_bundle_path / 'app_packages/PySide2/'

required_deps = set()


# FIXME pexpect.interact()
# if "-d" in sys.argv:
#     res = subprocess.run(f"{sys.executable} -m pudb {__file__} {app_module}",
#                             cwd= str(app_bundle_path / "app" / app_module),
#                             text=True,
#                             shell=True,
#                             )
#     sys.exit(res.returncode)


def run_p(cmd, errors=False):
    return subprocess.run(cmd,
                          cwd = str(app_bundle_path / "app"),
                          text=True,
                          shell=True,
                          stderr=subprocess.STDOUT if errors else subprocess.PIPE,
                          stdout=subprocess.PIPE)


def find_app_deps(py_module):
    command = f"QT_DEBUG_PLUGINS=1 {sys.executable} -v -m {py_module} 2>&1"

    res = run_p(command + ' | grep --line-buffered -oP "loaded.*/.*?\.so[\.\d]*"', errors=True)

    if "Abort" in res.stdout or res.returncode != 0:
        res = run_p(command, errors=True)
        print(res.stdout)
        print(f"\nERROR: '{app_module}' module exited with code {res.returncode}. Abort deps gathering.")
        sys.exit(E_CODE_TARGET_ABORT)

    all_deps = res.stdout.splitlines()

    so_libs = {m.split('/')[-1] for m in all_deps}  # [!] cut filenames before filtering
    so_libs = {m for m in so_libs if ".so" in m and "python" not in m}

    print(so_libs)

    required_deps.update(so_libs)
    return required_deps


def find_elf_deps(libs):
    deps = set()

    if not ps2_path.exists():
        print(f"ERROR: app's path '{ps2_path}' doesn't exists")
        sys.exit(E_CODE_NO_PS2)

    for lib in libs:
        # collect all deps
        res = run_p(f"ldd $(find {ps2_path} -name {lib}) | egrep -v 'linux-vdso|ld-linux'")
        s = {l.strip().split(" => ")[0] for l in res.stdout.splitlines()}
        s = {l.split(' ')[0] for l in s}
        deps.update(s)

    print("@ Qt deps:\n", deps)
    return deps


def dpkg_resolve(libs):
    resolved = set()
    unresolved= set()

    for lib_path in libs:
        res = run_p(f"dpkg -S '{lib_path}'")
        # resolved.add(res.stdout.split(': ')[0])  # + suffix :amd64
        if not res.stdout.strip() \
                or "no path found" in res.stdout:
            unresolved.add(lib_path)
        elif res.stdout.strip():
            resolved.add(res.stdout.split(':')[0])
        else:
            print(f"@ WARNING: {lib_path}")

    print()
    print("@ dpkg resolved:\n", resolved)
    print("@ still unresolved:\n", resolved)
    return unresolved


def handle_dpkg_unresolved(libs):
    libs = list(libs)

    # first look at app_dir
    found_in_app_dir = look_at_app_dir(libs)
    print()
    print("@ found in APP_DIR:\n", found_in_app_dir, "\n")

    for found_lib in found_in_app_dir:
        for orig_lib in libs:
            if found_lib in orig_lib:
                libs.remove(orig_lib)

    print()
    print("@ total unresolved:\n", libs)

    # then find remaining dependencies in OS index
    if libs:
        lib_paths = '\n'.join(libs)
        res = run_p(f"echo '{lib_paths}' | apt-file find -f -", errors=True)

        packages = {l: set() for l in libs}  # initialize !

        for p in res.stdout.splitlines():
            pkg_name = p.split(": ")[0]
            lib_suggested_name = p.split(": ")[1]

            def resolve_lib_name(name):
                for l in libs:
                    if l in name:
                        return l
                return "#"

            lib_name = resolve_lib_name(lib_suggested_name)
            packages[lib_name].add(pkg_name)

        print()
        print("@ apt-file suggests:\n")
        for k, v in packages.items():
            print(f"> {k:20}: {list(v)}")


def look_at_app_dir(libs):
    libs = [l.split('/')[-1] for l in libs]  # extract libs' filenames from path-like strings
    found_in_app_dir = set()

    for lib in libs:
        res = run_p(f'find {app_bundle_path} -name "{lib}"')
        if res.returncode == 0 and res.stdout.strip():
            found_in_app_dir.add(lib)

    required_deps.update(found_in_app_dir)
    return found_in_app_dir


def calculate_size():
    return run_p(f"du -sh {ps2_path}").stdout.split('\t')[0]


def main():
    print("\n***************** APP DEPS *******************\n")
    app_deps = find_app_deps(app_module)

    print("\n************** RECURSIVE DEPS ****************\n")
    all_deps = find_elf_deps(app_deps)
    unresolved_deps = dpkg_resolve(all_deps)
    handle_dpkg_unresolved(unresolved_deps)

    print("\n********** REQUIRED PySide2 DEPS *************\n")
    print(required_deps)

    size_before = calculate_size()

    print()
    print("Clearing unused dependencies...")
    globbed_so = ps2_path.glob("**/*.so*")
    so_paths = [str(so) for so in globbed_so]

    for so_path in so_paths:
        so_name = str(so_path).split('/')[-1]

        # skip required deps
        if any(so_name in dep for dep in required_deps):
            continue

        run_p(f"rm {so_path}")

    for name in ["designer", "rcc", "uic", "pyside2-lupdate"]:
        run_p(f"find {ps2_path} -type f -name {name} -exec rm {{}} +")

    print("Done")
    print()

    size_after = calculate_size()
    print("PySide2 directory size before:", size_before)
    print("PySide2 directory size after:", size_after)
    print()


if __name__ == '__main__':
    main()
