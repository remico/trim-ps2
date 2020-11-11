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

import platform
import setuptools


if 'linux' not in platform.system().lower():
    raise OSError('Platform must be GNU Linux. Aborting installation...')


# make the distribution platform dependent
try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
    class bdist_wheel(_bdist_wheel):
        def finalize_options(self):
            _bdist_wheel.finalize_options(self)
            self.root_is_pure = False
            # self.plat_name_supplied = True
            # self.plat_name = "manylinux1_x86_64"
except ImportError:
    bdist_wheel = None


setuptools.setup(
    cmdclass={
        'bdist_wheel': bdist_wheel
    }
)
