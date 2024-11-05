import os
import platform
import subprocess
import sys
from os import path

from setuptools import Extension, find_packages, setup
from setuptools.command.develop import develop
from setuptools.command.egg_info import egg_info
from setuptools.command.install import install

AUTHOR_NAME = 'Jina AI'
AUTHOR_EMAIL = 'hello@jina.ai'
LICENSE = 'Apache 2.0'
GITHUB_REPO = 'https://github.com/jina-ai/jina/'
DOWNLOAD_URL = 'https://github.com/jina-ai/jina/tags'
DOCUMENTATION = 'https://jina.ai/serve'
TRACKER = 'https://github.com/jina-ai/jina/issues'

if sys.version_info < (3, 7, 0):
    raise OSError(f'Jina requires Python >=3.7, but yours is {sys.version}')

if (3, 7, 0) <= sys.version_info < (3, 8, 0):
    # https://github.com/pypa/setuptools/issues/926#issuecomment-294369342
    try:
        import fastentrypoints
    except ImportError:
        try:
            import pkg_resources
            from setuptools.command import easy_install

            easy_install.main(['fastentrypoints'])
            pkg_resources.require('fastentrypoints')
            import fastentrypoint
        except:
            pass

try:
    pkg_name = 'jina'
    libinfo_py = path.join(pkg_name, '__init__.py')
    libinfo_content = open(libinfo_py, 'r', encoding='utf-8').readlines()
    version_line = [l.strip() for l in libinfo_content if l.startswith('__version__')][
        0
    ]
    exec(version_line)  # gives __version__
except FileNotFoundError:
    __version__ = '0.0.0'

try:
    with open('README.md', encoding='utf-8') as fp:
        _long_description = fp.read()
except FileNotFoundError:
    _long_description = ''


def register_ac():
    import os
    import re
    from pathlib import Path

    home = str(Path.home())
    resource_path = 'jina/resources/completions/jina.%s'
    regex = r'#\sJINA_CLI_BEGIN(.*)#\sJINA_CLI_END'
    _check = {'zsh': '.zshrc', 'bash': '.bashrc', 'fish': '.fish'}

    def add_ac(k, v):
        v_fp = os.path.join(home, v)
        if os.path.exists(v_fp) or os.environ.get('SHELL', '').endswith(k):
            try:
                with open(v_fp, encoding='utf-8') as fp:
                    sh_content = fp.read()
            except FileNotFoundError:
                sh_content = ''
            with open(resource_path % k, encoding='utf-8') as fr:
                if re.findall(regex, sh_content, flags=re.S):
                    _sh_content = re.sub(regex, fr.read(), sh_content, flags=re.S)
                else:
                    _sh_content = sh_content + '\n\n' + fr.read()
            if _sh_content:
                with open(v_fp, 'w', encoding='utf-8') as fp:
                    fp.write(_sh_content)

    try:
        for k, v in _check.items():
            add_ac(k, v)
    except Exception:
        pass


class PostDevelopCommand(develop):
    """Post-installation for development mode."""

    def run(self):
        develop.run(self)
        register_ac()


class PostInstallCommand(install):
    """Post-installation for installation mode."""

    def run(self):
        install.run(self)
        register_ac()


class PostEggInfoCommand(egg_info):
    """Post-installation for egg info mode."""

    def run(self):
        egg_info.run(self)
        register_ac()


def get_extra_requires(path, add_all=True):
    import re
    from collections import defaultdict

    try:
        with open(path, encoding='utf-8') as fp:
            extra_deps = defaultdict(set)
            for k in fp:
                if k.strip() and not k.startswith('#'):
                    tags = set()
                    if ':' in k:
                        k, v = k.split(':')
                        tags.update(vv.strip() for vv in v.split(','))
                    tags.add(re.split('[<=>]', k)[0])
                    for t in tags:
                        extra_deps[t].add(k)

            # add tag `all` at the end
            if add_all:
                extra_deps['all'] = set(vv for v in extra_deps.values() for vv in v)

        return extra_deps
    except FileNotFoundError:
        return {}


all_deps = get_extra_requires('extra-requirements.txt')

core_deps = all_deps['core']
perf_deps = all_deps['perf'].union(core_deps)
standard_deps = all_deps['standard'].union(core_deps).union(perf_deps)

# uvloop is not supported on windows
perf_deps = {
    i + ";platform_system!='Windows'" if i.startswith('uvloop') else i
    for i in perf_deps
}
standard_deps = {
    i + ";platform_system!='Windows'" if i.startswith('uvloop') else i
    for i in standard_deps
}
for k in ['all', 'devel', 'cicd']:
    all_deps[k] = {
        i + ";platform_system!='Windows'" if i.startswith('uvloop') else i
        for i in all_deps[k]
    }

# by default, final deps is the standard deps, unless specified by env otherwise
final_deps = standard_deps

# Use env var to enable a minimum installation of Jina
# JINA_PIP_INSTALL_CORE=1 pip install jina
# JINA_PIP_INSTALL_PERF=1 pip install jina
if os.environ.get('JINA_PIP_INSTALL_CORE'):
    final_deps = core_deps
elif os.environ.get('JINA_PIP_INSTALL_PERF'):
    final_deps = perf_deps

extra_golang_kw = {}

ret_code = -1

try:
    ret_code = subprocess.run(['go', 'version']).returncode
except Exception:
    pass

is_mac_os = platform.system() == 'Darwin'
is_windows_os = platform.system() == 'Windows'
is_37 = sys.version_info.major == 3 and sys.version_info.minor == 7

if ret_code == 0 and not is_windows_os and (not is_mac_os or not is_37):
    extra_golang_kw = {
        'build_golang': {'root': 'jraft', 'strip': False},
        'ext_modules': [
            Extension(
                'jraft',
                ['jina/serve/consensus/run.go'],
                py_limited_api=True,
                define_macros=[('Py_LIMITED_API', None)],
            )
        ],
        'setup_requires': ['setuptools-golang'],
    }

setup(
    name=pkg_name,
    packages=find_packages(),
    version=__version__,
    include_package_data=True,
    description='Multimodal AI services & pipelines with cloud-native stack: gRPC, Kubernetes, Docker, OpenTelemetry, Prometheus, Jaeger, etc.',
    author=AUTHOR_NAME,
    author_email=AUTHOR_EMAIL,
    license=LICENSE,
    url=GITHUB_REPO,
    download_url=DOWNLOAD_URL,
    long_description=_long_description,
    long_description_content_type='text/markdown',
    zip_safe=False,
    install_requires=list(final_deps),
    extras_require=all_deps,
    entry_points={
        'console_scripts': [
            'jina=jina_cli:main',
        ],
    },
    cmdclass={
        'develop': PostDevelopCommand,
        'install': PostInstallCommand,
        'egg_info': PostEggInfoCommand,
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: Education',
        'Intended Audience :: Science/Research',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Unix Shell',
        'Environment :: Console',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Topic :: Database :: Database Engines/Servers',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
        'Topic :: Internet :: WWW/HTTP :: Indexing/Search',
        'Topic :: Scientific/Engineering :: Image Recognition',
        'Topic :: Multimedia :: Video',
        'Topic :: Scientific/Engineering',
        'Topic :: Scientific/Engineering :: Mathematics',
        'Topic :: Software Development',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    project_urls={
        'Documentation': DOCUMENTATION,
        'Source': GITHUB_REPO,
        'Tracker': TRACKER,
    },
    keywords='jina cloud-native cross-modal multimodal neural-search query search index elastic neural-network encoding '
    'embedding serving docker container image video audio deep-learning mlops',
    **extra_golang_kw,
)
