#!/bin/bash
set -e

cd /tmp

echo '=== Downloading Python 3.12.9 ===' 
curl -L -o python312.tgz https://www.python.org/ftp/python/3.12.9/Python-3.12.9.tgz --max-time 120 2>&1
if [ ! -s python312.tgz ]; then
    echo 'FALLBACK: github mirror...'
    curl -L -o python312.tgz https://github.com/python/cpython/archive/refs/tags/v3.12.9.tar.gz --max-time 180
fi

echo '=== Extracting ==='
tar xzf python312.tgz
cd Python-3.12.9

echo '=== Configuring ==='
./configure --prefix=/usr/local/python312 --enable-shared --with-lto \
    LDFLAGS='-Wl,-rpath,/usr/local/python312/lib' > /tmp/py_build.log 2>&1
echo 'CONFIGURE_OK'

echo '=== Compiling (-j2) ==='
make -j2 >> /tmp/py_build.log 2>&1
echo 'MAKE_OK'

echo '=== Installing ==='
make altinstall >> /tmp/py_build.log 2>&1
echo 'INSTALL_OK'

echo '=== Symlinks ==='
mv /usr/bin/python3 /usr/bin/python3.11.bak 2>/dev/null || true
ln -sf /usr/local/python312/bin/python3.12 /usr/bin/python3
ln -sf /usr/local/python312/bin/python3.12 /usr/bin/python3.12

echo '=== ldconfig ==='
echo '/usr/local/python312/lib' > /etc/ld.so.conf.d/python312.conf
ldconfig

echo '=== Verify ==='
python3 --version
/usr/local/python312/bin/pip3.12 --version 2>/dev/null || echo '(pip needs get-pip.py)'

echo 'BUILD_COMPLETE'
