#!/bin/bash
# Script to build Tribler Debian package.
# Note: Run the script from root directory, eg.
# ./build/debian/build-snap.sh

if [[ ! -d build/debian ]]
then
  echo "Please run this script from project root as:\n./build/debian/build-snap.sh"
fi


if [[ ! -f ".snapcraft.yaml" ]]; then
    echo "snapcraft.yaml does not exist in $PWD. Please make sure to execute the script from the project root directory."
    exit 1
fi

if [[ ! -d build/debian/tribler/usr/share/tribler ]]
then
  echo "Snap package depends on PyInstaller based Debian package. Building .deb package first..."
  build/debian/makedist_debian.sh
fi

# Make sure we have the latest packages
#apt-get update

BUILD_ARGS=${SNAP_BUILD_ARGS:-''}
snapcraft $BUILD_ARGS
