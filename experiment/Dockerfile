# Dockerfile to build Tribler core image used for experiments.

# The base image: 'triblercore/libtorrent:1.2.10-x' is a separately compiled version of libtorrent with BEP33 support.
# Check: https://jenkins-ci.tribler.org/job/docker/job/build-libtorrent/
# Note: permission is required to access Jenkins job configuration.

# Usage: run docker build from the project root (tribler) directory
# Eg. docker build -t triblercore/experiment:torrent_health -f experiment/Dockerfile .

FROM triblercore/libtorrent:1.2.10-x

# Update the base system and install required non-pip dependencies
RUN apt update && apt upgrade -y
RUN apt install -y libsodium23 python3-pip git

# Add a non-previleged user
USER root
RUN groupadd -r tribler -g 901 && \
    useradd -u 901 -r -g tribler -m -d /home/tribler -s /sbin/nologin -c "tribler user" tribler && \
    chmod 755 /opt

WORKDIR /opt

# Install pip dependencies first
COPY ./src/requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

# Copy the source
COPY ./src ./src

# Copy experiments and install pip dependencies
COPY ./experiment ./experiment
RUN pip3 install -r ./experiment/requirements.txt

# Expose ports
EXPOSE 7759 8085

ENV PYTHONPATH="src/pyipv8:src/tribler-common:src/tribler-core:."

RUN chown -R tribler:tribler /opt/
USER tribler

# Define the command to run
CMD ["/usr/bin/python3", "src/experiment/popularity_community/network_experiment.py"]