#!/bin/bash
cd libnice
mkdir -p build
NOCONFIGURE=1 ./autogen.sh
./configure --prefix=$PWD/build --disable-static --with-gstreamer-0.10=no --enable-gtk-doc --enable-introspection
sed -i -e 's/ -shared / -Wl,-O1,--as-needed\0/g' libtool
make