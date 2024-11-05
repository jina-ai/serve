# On Apple Silicon

If you own a macOS device with an Apple Silicon M1/M2 chip, you can run Jina-serve **natively** on it (instead of running under Rosetta) and enjoy up to 10x faster performance. This chapter summarizes how to install Jina-serve.

## Check terminal and device

To ensure you are using the right terminal, run:

```bash
uname -m
```

It should return:

```text
arm64
```


## Install Homebrew

`brew` is a package manager for macOS. If you have already installed it, you need to confirm it is actually installed for Apple Silicon not for Rosetta. To check that, run:

```bash
which brew
```

```text
/opt/homebrew/bin/brew
```

If it's installed under `/usr/local/` instead of `/opt/homebrew/`, it means your `brew` is installed for Rosetta not for Apple Silicon. You need to [reinstall it](https://apple.stackexchange.com/a/410829).

```{danger}
Reinstalling `brew` can be a destructive operation. Ensure you have backed up your data before proceeding.
```

To (re)install brew, run:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

You can observe the output to check if it contains `/opt/homebrew` to ensure you are installing for Apple Silicon.

## Install Python

Python also has to be installed for Apple Silicon. It is possible it is installed for Rosetta, and you are not aware of that. To confirm, run:

```python
import platform

platform.machine()
```

This should output:

```text
'arm64'
```

If not, then you are using Python under Rosetta, and you need to install Python for Apple Silicon with `brew`:


```bash
brew install python3
```

As of August 2022, this will install Python 3.10 natively for Apple Silicon.

Ensure you note down where `python` and `pip` are installed. In this example, they are installed to `/opt/homebrew/bin/python3` and `/opt/homebrew/opt/python@3.10/libexec/bin/pip` respectively.

## Install dependencies wheels

There are some core dependencies that Jina-serve needs to run, whose wheels are not available on PyPI but fortunately are available as wheels. To install them, run:

```bash
brew install protobuf numpy
```

## Install Jina-serve

Now we can install Jina-serve via `pip`. Ensure you use the correct `pip`:

```bash
/opt/homebrew/opt/python@3.10/libexec/bin/pip install jina
```

`grpcio` requires building the wheels, it will take some time.

Note: If the previous step fails, adding the environment variables below might solve the problem:

```bash
export GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1
export GRPC_PYTHON_BUILD_SYSTEM_ZLIB=1
```

After all the dependencies are installed, you can run Jina-serve CLI and check the system information.

```bash
jina -vf
```

```{code-block} text
---
emphasize-lines: 13-15
---
- jina 3.7.14
- docarray 0.15.4
- jcloud 0.0.35
- jina-hubble-sdk 0.16.1
- jina-proto 0.1.13
- protobuf 3.20.1
- proto-backend python
- grpcio 1.47.0
- pyyaml 6.0
- python 3.10.6
- platform Darwin
- platform-release 21.6.0
- platform-version Darwin Kernel Version 21.6.0: Sat Jun 18 17:07:28 PDT 2022; root:xnu-8020.140.41~1/RELEASE_ARM64_T8110
- architecture arm64
- processor arm
- uid 94731629138370
- session-id 49497356-254e-11ed-9624-56286d1a91c2
- uptime 2022-08-26T16:49:28.279723
- ci-vendor (unset)
* JINA_DEFAULT_HOST (unset)
* JINA_DEFAULT_TIMEOUT_CTRL (unset)
* JINA_DEPLOYMENT_NAME (unset)
* JINA_DISABLE_UVLOOP (unset)
* JINA_EARLY_STOP (unset)
* JINA_FULL_CLI (unset)
* JINA_GATEWAY_IMAGE (unset)
* JINA_GRPC_RECV_BYTES (unset)
* JINA_GRPC_SEND_BYTES (unset)
* JINA_HUB_NO_IMAGE_REBUILD (unset)
* JINA_LOG_CONFIG (unset)
* JINA_LOG_LEVEL (unset)
* JINA_LOG_NO_COLOR (unset)
* JINA_MP_START_METHOD (unset)
* JINA_OPTOUT_TELEMETRY (unset)
* JINA_RANDOM_PORT_MAX (unset)
* JINA_RANDOM_PORT_MIN (unset)
```


Congratulations! You have successfully installed Jina-serve on Apple Silicon.


````{tip}

To install MPS-enabled PyTorch, run:

```bash
/opt/homebrew/opt/python@3.10/libexec/bin/pip install -U --pre torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/nightly/cpu
```
````




