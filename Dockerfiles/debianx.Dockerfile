# !!! An ARG declared before a FROM is outside of a build stage, so it can’t be used in any instruction after a FROM
ARG PY_VERSION=3.10

FROM python:${PY_VERSION}-slim AS jina_dep

# a "cache miss" occurs upon its first usage, not its definition.

# given by builder
ARG PIP_TAG
# something like "gcc libc-dev make libatlas-base-dev ruby-dev"
ARG APT_PACKAGES="gcc libc-dev"

# given by builder's env
ARG VCS_REF
ARG PY_VERSION
ARG BUILD_DATE
ARG JINA_VERSION
ARG TARGETPLATFORM
ARG PIP_EXTRA_INDEX_URL="https://www.piwheels.org/simple"
ARG PIP_INSTALL_CORE
ARG PIP_INSTALL_PERF

# constant, wont invalidate cache
LABEL org.opencontainers.image.vendor="Jina AI Limited" \
      org.opencontainers.image.licenses="Apache 2.0" \
      org.opencontainers.image.title="Jina" \
      org.opencontainers.image.description="Build multimodal AI services via cloud native technologies" \
      org.opencontainers.image.authors="hello@jina.ai" \
      org.opencontainers.image.url="https://github.com/jina-ai/jina" \
      org.opencontainers.image.documentation="https://jina.ai/serve"

# constant, wont invalidate cache
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    JINA_PIP_INSTALL_CORE=${PIP_INSTALL_CORE} \
    JINA_PIP_INSTALL_PERF=${PIP_INSTALL_PERF}

# change on extra-requirements.txt, setup.py will invalid the cache
COPY extra-requirements.txt setup.py /tmp/


RUN cd /tmp/ && \
    # apt latest security packages should be install before pypi package
    if [ -n "${APT_PACKAGES}" ]; then apt-get update && apt-get upgrade -y && \
    apt-get --only-upgrade install openssl -y && \
    apt-get install --no-install-recommends -y ${APT_PACKAGES}; fi && \
    if [ $PY_VERSION==3.11 ]; then apt-get install --no-install-recommends -y build-essential ; fi && \
    if [ -n "${PIP_TAG}" ]; then pip install --default-timeout=1000 --compile --extra-index-url $PIP_EXTRA_INDEX_URL ".[${PIP_TAG}]" ; fi && \
    pip install --default-timeout=1000 --compile --extra-index-url ${PIP_EXTRA_INDEX_URL} . && \
    # now remove apt packages
    if [ -n "${APT_PACKAGES}" ]; then apt-get remove -y --auto-remove ${APT_PACKAGES} && apt-get autoremove && apt-get clean && rm -rf /var/lib/apt/lists/*; fi && \
    rm -rf /tmp/* && rm -rf /jina


FROM jina_dep AS jina

# the following label use ARG hence will invalid the cache
LABEL org.opencontainers.image.created=${BUILD_DATE} \
      org.opencontainers.image.source="https://github.com/jina-ai/jina/commit/${VCS_REF}" \
      org.opencontainers.image.version=${JINA_VERSION} \
      org.opencontainers.image.revision=${VCS_REF}

# the following env use ARG hence will invalid the cache
ENV JINA_VERSION=${JINA_VERSION} \
    JINA_VCS_VERSION=${VCS_REF} \
    JINA_BUILD_DATE=${BUILD_DATE}

# copy will almost always invalid the cache
COPY . /jina/

# install jina again but this time no deps
RUN cd /jina && \
    pip install --no-deps --compile . && \
    rm -rf /tmp/* && rm -rf /jina

ENTRYPOINT ["jina"]


