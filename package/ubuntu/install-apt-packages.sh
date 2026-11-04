#!/bin/bash
set -euox pipefail

# Update package lists quietly
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends gpg ca-certificates

# Ubuntu 26.04 ships PySide6 and Qt6 in its own archive. No extra repository is needed.
packages=(
  build-essential
  ccache
  cmake
  doxygen
  graphviz
  imagemagick
  libboost-date-time-dev
  libboost-dev
  libboost-filesystem-dev
  libboost-graph-dev
  libboost-iostreams-dev
  libboost-program-options-dev
  libboost-regex-dev
  libboost-serialization-dev
  libboost-thread-dev
  libcoin-dev
  libeigen3-dev
  libexpat1-dev
  libgtest-dev
  libgmock-dev
  libharfbuzz-dev
  libkdtree++-dev
  libmedc-dev
  libocct-data-exchange-dev
  libocct-ocaf-dev
  libocct-visualization-dev
  libopencamlib-dev
  libproj-dev
  libpcl-dev
  libpyside6-dev
  qt6-svg-dev
  libspnav-dev
  libvtk9-dev
  libx11-dev
  libxerces-c-dev
  libyaml-cpp-dev
  libzipios++-dev
  netgen
  netgen-headers
  ninja-build
  nlohmann-json3-dev
  occt-draw
  pyside6-tools
  python3-cxx-dev
  python3-av
  python-is-python3
  python3-dev
  python3-defusedxml
  python3-git
  python3-lark
  python3-markdown
  python3-matplotlib
  python3-opencamlib
  python3-packaging
  python3-pip
  python3-ply
  python3-pybind11
  python3-pivy
  python3-pyside6.qtcore
  python3-pyside6.qtgui
  python3-pyside6.qtnetwork
  python3-pyside6.qtsvg
  python3-pyside6.qtsvgwidgets
  python3-pyside6.qtwidgets
  qt6-base-dev
  qt6-l10n-tools
  qt6-tools-dev
  qt6-tools-dev-tools
  swig
  xvfb
)

# Install all packages
sudo apt-get install -y --no-install-recommends "${packages[@]}"
