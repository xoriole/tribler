FROM ubuntu:18.04
# Make the GUI work in a container
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /usr/src/tribler


# Installing dependencies and cleaning up afterwards
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    python3 python-dev python3-dev \
    build-essential libssl-dev libffi-dev \
    libxml2-dev libxslt1-dev zlib1g-dev \
    python3-setuptools\
    python3-pip \
    python3-libtorrent \
    libsodium23

COPY requirements.txt ./
COPY pip3-requirements-core.txt ./
RUN pip3 install --no-cache-dir -r pip3-requirements-core.txt

RUN git clone --recursive https://github.com/xoriole/tribler.git && \
    cd tribler && \
    git checkout docker-core && \
    python3 Tribler/Main/Build/update_version_from_git.py

EXPOSE 8085
WORKDIR /usr/src/tribler/tribler
CMD [ "python3", "run_core.py" ]

