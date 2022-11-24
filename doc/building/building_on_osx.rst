This guide explains how to build Tribler on MacOS (10.10 to 10.13). The final result is a ``.dmg`` file which, when opened, allows ``Tribler.app`` to be copied to the Applications directory and or launched. Make sure the required packages required by Tribler are installed
from the  `Development instructions <../development/development_on_osx.rst>`_.

Required packages
-------------------
* eulagise: In order to attach the EULA to the ``.dmg`` file, we make use of the ``eulagise`` script. This script is written in PERL and is based on a more fully-featured script. The script can be downloaded from `GitHub <https://github.com/CompoFX/compo/blob/master/tool/eulagise.pl>`_. The builder expects the script to be executable and added to the ``PATH`` environment variable. This can be done with the following commands:

.. code-block:: none

    cp eulagise.pl /usr/local/bin/eulagise
    chmod +x /usr/local/bin/eulagise
    eulagise # to test it - it should show that you should add some flags

Building Tribler on macOS
-------------------------
Start by checking out the directory you want to clone (using ``git clone``). Open a terminal and ``cd`` to this new cloned directory (referenced to as ``tribler_source`` in this guide).

Next, we should inject version information into the files about the latest release. `git` is used to find the latest tag and commit which is to determine the version. Invoke it from the following commands from ``tribler_source`` project directory.

.. code-block:: none

    # Sentry is used for error reporting so SENTRY_URL environment variable is expected.
    # It can be left empty but the environment variable is required to exist.
    export SENTRY_URL=

    git describe --tags | python -c "import sys; print(next(sys.stdin).lstrip('v'))" > .TriblerVersion
    git rev-parse HEAD > .TriblerCommit
    export TRIBLER_VERSION=$(head -n 1 .TriblerVersion)

    python3 ./build/update_version.py -r .

Now execute the builder with the following command:

.. code-block:: none

    build/mac/makedist_macos.sh

This will create the ``.dmg`` file in the ``tribler_source/dist`` directory.
