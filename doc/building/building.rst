================
Building Tribler
================

This page contains instructions on how to build and package Tribler.

Windows
=======

.. include:: building_on_windows.rst

MacOS
=====

.. include:: building_on_osx.rst

Debian and derivatives
======================

Run the following commands in your terminal:

.. code-block:: none

    sudo apt-get install devscripts python-setuptools fonts-noto-color-emoji

    # Sentry is used for error reporting so SENTRY_URL environment variable is expected.
    # It can be left empty but the environment variable is required to exist.
    export SENTRY_URL=

    cd tribler
    git describe --tags | python -c "import sys; print(next(sys.stdin).lstrip('v'))" > .TriblerVersion
    git rev-parse HEAD > .TriblerCommit
    export TRIBLER_VERSION=$(head -n 1 .TriblerVersion)

    python3 ./build/update_version.py -r .
    ./build/debian/makedist_debian.sh

This will build a ``tribler.deb`` file, including all dependencies and required libraries.

Other Unixes
============

We don't have a generic setup.py yet.

So for the time being, the easiest way to package Tribler is to put ``Tribler/`` in ``/usr/share/tribler/`` and ``debian/bin/tribler`` in ``/usr/bin/``. A good reference for the dependency list is ``debian/control``.
