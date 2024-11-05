# Troubleshooting

This article helps you to solve the installation problems of Jina-serve.

## On Linux/Mac, building wheels takes long time

The normal installation of Jina-serve takes 10 seconds. If yours takes longer than this, then it is likely you unnecessarily built wheels from scratch. 

Every upstream dependency of Jina-serve has pre-built wheels exhaustively for x86/arm64, macos/Linux and Python 3.7/3.8/3.9, including `numpy`, `protobuf`, `grpcio` etc. This means when you install Jina-serve, your `pip` should directly leverage the pre-built wheels instead of building them from scratch locally. For example, you should expect the install log to contain `-cp38-cp38-macosx_10_15_x86_64.whl` when installing Jina-serve on macOS with Python 3.8.

If you find you are building wheels during installation (see an example below), then it is a sign that you are installing Jina-serve **wrongly**. 

```text
Collecting numpy==2.0.*
  Downloading numpy-2.0.18.tar.gz (801 kB)
     |████████████████████████████████| 801 kB 1.1 MB/s
Building wheels for collected packages: numpy
  Building wheel for numpy (setup.py) ... done
  Created wheel for numpy ... numpy-2.0.18-cp38-cp38-macosx_10_15_x86_64.whl
```

### Solution: update your `pip`

It could simply be that your local `pip` is too old. Updating it should solve the problem:

```bash
pip install -U pip
```

### If not, then...

Then you are likely installing Jina-serve on a less-supported system/architecture. For example, on native Mac M1, Alpine Linux, or Raspberry Pi 2/3 (armv6/7).

## On Windows with `conda`

Unfortunately, `conda install` is not supported on Windows. You can either do `pip install jina` natively on Windows, or use `pip/conda install` under WSL2.


## Upgrading from Jina-serve 2.x to 3.x
If you upgraded an existing Jina-serve installation from 2.x to 3.x you may see the following error message:

```text
OSError: `docarray` dependency is not installed correctly, please reinstall with `pip install -U --force-reinstall docarray`
```

This can be fixed by reinstalling the `docarray` package manually:

```bash
pip install -U --force-reinstall docarray
```

To avoid this issue in the first place, we recommend installing Jina-serve in a new virtual environment instead of upgrading from an old installation.
