# Via Docker Image

Our universal Docker image is ready-to-use on linux/amd64 and linux/arm64. The Docker image name always starts with `jinaai/jina` followed by a tag composed of three parts:

```text
jinaai/jina:{version}{python_version}{extra}
```

- `{version}`: The version of Jina-serve. Possible values:
    - `latest`: the last release;
    - `master`: the master branch of `jina-ai/jina` repository;
    - `x.y.z`: the release of a particular version;
    - `x.y`: the alias to the last `x.y.z` patch release, i.e. `x.y` = `x.y.max(z)`;
- `{python_version}`: The Python version of the image. Possible values:
    - ` `, `-py37`: Python 3.7;
    - `-py38` for Python 3.8;
    - `-py39` for Python 3.9;
- `{extra}`: the extra dependency installed along with Jina-serve. Possible values:
    - ` `: Jina is installed inside the image with minimum dependencies `pip install jina`;
    - `-perf`: Jina is installed inside the image via `pip install jina`. It includes all performance dependencies; 
    - `-standard`: Jina is installed inside the image via `pip install jina`. It includes all recommended dependencies;  
    - `-devel`: Jina is installed inside the image via `pip install "jina[devel]"`. It includes `standard` plus some extra dependencies;

Examples:

- `jinaai/jina:0.9.6`: the `0.9.6` release with Python 3.7 and the entrypoint of `jina`.
- `jinaai/jina:latest`: the latest release with Python 3.7 and the entrypoint of `jina`
- `jinaai/jina:master`: the master with Python 3.7 and the entrypoint of `jina`

## Image alias and updates

| Event | Updated images | Aliases |
| --- | --- | --- |
| On Master Merge | `jinaai/jina:master{python_version}{extra}` | |
| On `x.y.z` release | `jinaai/jina:x.y.z{python_version}{extra}` | `jinaai/jina:latest{python_version}{extra}`, `jinaai/jina:x.y{python_version}{extra}` |

12 images are built, i.e. taking the combination of:
  - `{python_version} = ["-py37", "-py38", "-py39"]`
  - `{extra} = ["", "-devel", "-standard", "-perf"]`


## Image size on different tags

```{warning}
[Due to a known bug in shields.io/Docker Hub API](https://github.com/badges/shields/issues/7583), the following badge may show "invalid" status randomly.
```

|Image Size|
| ---|
|![](https://img.shields.io/docker/image-size/jinaai/jina/latest?label=jinaai%2Fjina%3Alatest&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/latest-py38?label=jinaai%2Fjina%3Alatest-py38&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/latest-py39?label=jinaai%2Fjina%3Alatest-py39&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/latest-devel?label=jinaai%2Fjina%3Alatest-devel&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/latest-perf?label=jinaai%2Fjina%3Alatest-perf&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/latest-standard?label=jinaai%2Fjina%3Alatest-standard&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/latest-py38-devel?label=jinaai%2Fjina%3Alatest-py38-devel&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/latest-py38-perf?label=jinaai%2Fjina%3Alatest-py38-perf&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/latest-py38-standard?label=jinaai%2Fjina%3Alatest-py38-standard&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/latest-py39-devel?label=jinaai%2Fjina%3Alatest-py39-devel&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/latest-py39-perf?label=jinaai%2Fjina%3Alatest-py39-perf&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/latest-py39-standard?label=jinaai%2Fjina%3Alatest-py39-standard&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/master?label=jinaai%2Fjina%3Amaster&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/master-py38?label=jinaai%2Fjina%3Amaster-py38&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/master-py39?label=jinaai%2Fjina%3Amaster-py39&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/master-devel?label=jinaai%2Fjina%3Amaster-devel&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/master-perf?label=jinaai%2Fjina%3Amaster-perf&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/master-standard?label=jinaai%2Fjina%3Amaster-standard&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/master-py38-devel?label=jinaai%2Fjina%3Amaster-py38-devel&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/master-py38-perf?label=jinaai%2Fjina%3Amaster-py38-perf&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/master-py38-standard?label=jinaai%2Fjina%3Amaster-py38-standard&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/master-py39-devel?label=jinaai%2Fjina%3Amaster-py39-devel&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/master-py39-perf?label=jinaai%2Fjina%3Amaster-py39-perf&logo=docker)|
|![](https://img.shields.io/docker/image-size/jinaai/jina/master-py39-standard?label=jinaai%2Fjina%3Amaster-py39-standard&logo=docker)|
