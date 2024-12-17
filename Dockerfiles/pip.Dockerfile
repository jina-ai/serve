ARG PY_VERSION=3.10
ARG PIP_TAG

FROM python:${PY_VERSION}-slim

RUN apt-get update && apt-get install --no-install-recommends -y gcc libc6-dev pkg-config wget

RUN if [[ $PY_VERSION==3.11 ]]; then apt-get install --no-install-recommends -y build-essential ; fi

# Download and extract Go 1.19
RUN wget -q https://golang.org/dl/go1.19.linux-amd64.tar.gz \
    && tar -C /usr/local -xzf go1.19.linux-amd64.tar.gz \
    && rm go1.19.linux-amd64.tar.gz

# Set up environment variables for Go
ENV PATH="/usr/local/go/bin:${PATH}"
ENV GOPATH="/go"
ENV GOBIN="/go/bin"

COPY . /jina/

RUN cd /jina && pip install ."$PIP_TAG"
RUN cat $HOME/.bashrc
RUN grep -Fxq "# JINA_CLI_BEGIN" $HOME/.bashrc

ENTRYPOINT ["jina"]