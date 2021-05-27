#
# Copyright 2021 Joyent, Inc.
#

#
# This is a modified version of the common Dockerfile.packages, needed so that
# we can template values defined in the packet-baremetal component. Since
# the Equinix packet-images.git build scripts don't pass ARG values on the
# command line, we use sed replacements for %%VALUES%% in this script to
# declare defaults. The resulting Dockerfile and proto area can be then
# committed to a branch on a fork of the packet-images.git repository.
# This Dockerfile also ensures that epel-release gets installed before other
# packages. Note that the proto area that we drop into the image gets installed
# in to /, not /root.
#

FROM centos_7-base

ARG stamp=main-20210527T152228Z-g5202d78
ARG version=1.0
ARG image_desc="Joyent Storage Packet Baremetal Image"
ARG image_name=storage-packet-baremetal
ARG git_url=https://github.com/joyent/storage-gage-infra.git
ARG pip_packages=docker==4.4.4 websocket-client==0.59.0 boto3

# Install the epel package first so that that yum repo source is present for
# the rest of the packages.
ARG first_pkgs=' \
    epel-release-7-11'

ARG pkgs=' bash-completion-2.1-8.el7 bind-utils-9.11.4-26.P2.el7_9.5 cronie-1.4.11-23.el7 e2fsprogs-libs-1.42.9-19.el7 gettext-0.19.8.1-3.el7 initscripts-9.49.53-1.el7_9.1.x86_64 iperf3-3.1.7-2.el7.x86_64 iproute-4.11.0-30.el7 jq-1.6-2.el7 libcgroup-tools-0.41-21.el7 net-tools-2.0-0.25.20131004git.el7 nmon-16g-3.el7 openssh-clients-7.4p1-21.el7.x86_64 openssh-server-7.4p1-21.el7 python2-pip-8.1.2-14.el7 python3-3.6.8-18.el7 rsyslog-8.24.0-57.el7_9 smartmontools-7.0-2.el7 strace-4.24-6.el7 sudo-1.8.23-10.el7_9.1 wget-1.14-18.el7_6.1 http://10.33.140.165/gage-packages/kernel/4.14.4-1/kernel-ml-4.14.4-1.el7.elrepo.x86_64.rpm http://10.33.140.165/gage-packages/kernel/5.7.10-1/kernel-ml-5.7.10-1.el7.elrepo.x86_64.rpm ansible-2.9.21-1.el7 docker-ce-20.10.3-3.el7 pciutils-3.5.1-3.el7 pigz-2.3.4-1.el7 python-docker-py-1.10.6-11.el7 python-netaddr-0.7.5-9.el7 python2-pip-8.1.2-14.el7 unzip-6.0-21.el7 git-1.8.3.1-23.el7_8.x86_64'

LABEL storage.baremetal.version=${version} \
    storage.baremetal.stamp=${stamp} \
    storage.baremetal.name=${image_name} \
    storage.baremetal.desc=${image_desc} \
    storage.baremetal.git_url=${git_url} \
    storage.container.uuid=''

COPY proto /

#
# Install the packages we need, clean the yum db and enable docker
#
RUN curl -o /etc/yum.repos.d/docker-ce.repo \
        https://download.docker.com/linux/centos/docker-ce.repo && \
    yum install -y ${first_pkgs} && \
    yum install -y ${pkgs} && \
    yum clean all && \
    pip install --no-cache-dir ${pip_packages} && \
    { echo stamp: ${stamp}; \
      echo version: ${version};\
      echo image_desc: ${image_desc}; \
      echo image_name: ${image_name}; \
      echo git_url: ${git_url}; \
    } > /etc/joyent-storage.yml && \
    systemctl enable docker

