FROM ubuntu:18.04

ENV DEBIAN_FRONTEND=noninteractive

# APT dependencies; PIP dependencies are installed separately
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    python3 python-dev python3-dev \
    build-essential libssl-dev libffi-dev \
    libxml2-dev libxslt1-dev zlib1g-dev \
    python3-setuptools\
    python3-pip \
    python3-libtorrent \
    libsodium23

ENV HOME /home/tribler
ENV API_PORT 8085

# Create a local tribler user and set the working directory
RUN useradd -m --home-dir $HOME tribler && chown -R tribler:tribler $HOME
USER tribler
WORKDIR $HOME

# Set building arguments
ARG REPO_URL=https://github.com/xoriole/tribler.git
ARG VERSION=docker-core

COPY pip3-requirements-core.txt ./
RUN pip3 install --no-cache-dir -r pip3-requirements-core.txt

# Get code from the repository, install required pip dependencies & update the version from git
RUN git clone --recursive --depth 1 ${REPO_URL} -b ${VERSION} tribler

EXPOSE $API_PORT

WORKDIR $HOME/tribler
COPY run_core.py ./
CMD [ "python3", "run_core.py" ]

