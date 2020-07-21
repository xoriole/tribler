#!/bin/bash
# Script to build Tribler Debian package.
# Note: Run the script from root directory, eg.
# ./build/debian/makedist_debian.sh

if [[ ! -d build/debian ]]
then
  echo "Please run this script from project root as:\n./build/debian/makedist_debian.sh"
fi

rm -rf build/tribler
rm -rf dist/tribler
rm -rf build/debian/tribler/usr/share/tribler

python3 build/update_version_from_git.py

python3 -m PyInstaller tribler.spec

cp -r dist/tribler build/debian/tribler/usr/share/tribler

sed -i "s/__VERSION__/$(cat .TriblerVersion)/g" build/debian/tribler/DEBIAN/control
if [[ -f ".snapcraft.yaml" ]]; then
    sed -i "s/__VERSION__/$(cat .TriblerVersion)/g" .snapcraft.yaml
fi


dpkg-deb -b build/debian/tribler tribler_$(cat .TriblerVersion)_all.deb

## Build Tribler snap if $BUILD_TRIBLER_SNAP
#if [ "$BUILD_TRIBLER_SNAP" == "false" ]; then
#  exit 0
#fi
#
## Build snap with docker if exists
#if [ "$BUILD_SNAP_IN_DOCKER" == "true" ]; then
#    echo "Running snapcraft in docker"
#    cd build/debian && docker run -v "$PWD":/debian -w /debian triblertester/snap_builder:core18 /bin/bash ./build-snap.sh
#else
#    cd build/debian || exit 1
#    BUILD_ARGS=${SNAP_BUILD_ARGS:-''}
#    snapcraft clean
#    snapcraft $BUILD_ARGS
#fi