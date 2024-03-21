FROM python:3.9.19-alpine

ARG VCS_REF
ARG BUILD_DATE
ARG JINA_VERSION

LABEL org.opencontainers.image.created=$BUILD_DATE \
      org.opencontainers.image.authors="dev-team@jina.ai" \
      org.opencontainers.image.url="https://jina.ai" \
      org.opencontainers.image.documentation="https://docs.jina.ai" \
      org.opencontainers.image.source="https://github.com/jina-ai/jina/commit/$VCS_REF" \
      org.opencontainers.image.version=$JINA_VERSION \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.vendor="Jina AI Limited" \
      org.opencontainers.image.licenses="Apache 2.0" \
      org.opencontainers.image.title="Jina" \
      org.opencontainers.image.description="Jina is the cloud-native neural search solution powered by state-of-the-art AI and deep learning technology"

COPY . /jina/

ENV PYTHONPATH=$PYTHONPATH:/usr/lib/python3.8/dist-packages:/usr/local/lib/python3.8/site-packages:/usr/lib/python3/dist-packages:/usr/local/lib/python3/site-packages \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    JINA_VCS_VERSION=$VCS_REF \
    JINA_BUILD_DATE=$BUILD_DATE

# py3-scipy
RUN apk add --no-cache py3-pyzmq py3-numpy grpc && \
    ln -s locale.h /usr/include/xlocale.h && \
    cd /jina && \
    pip install . --compile && \
    find /usr/lib/python3.8/ -name 'tests' -exec rm -r '{}' + && \
    find /usr/lib/python3.8/site-packages/ -name '*.so' -print -exec sh -c 'file "{}" | grep -q "not stripped" && strip -s "{}"' \; && \
    rm /usr/include/xlocale.h && \
    rm -rf /tmp/* && \
    rm -rf /jina && \
    rm -rf /var/cache/apk/*

ENTRYPOINT ["jina"]