# trim-ps2
Analyses what the PySide2 modules a python package depends on, then remove all unused modules.
It is intended to be invoked by the [modified](https://github.com/remico/briefcase) `briefcase` tool
during AppImage build process on Linux platform.

:information_source: This distribution is GNU Linux-only, since it relies on a bunch of linux command line tools 
