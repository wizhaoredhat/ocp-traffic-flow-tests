FROM quay.io/centos/centos:stream9

RUN dnf install -y 'dnf-command(config-manager)'

RUN dnf config-manager --set-enabled crb

RUN dnf install -y epel-next-release epel-release

RUN dnf install \
        --allowerasing \
        /usr/bin/python \
        coreutils \
        ethtool \
        git \
        httpd \
        iperf3 \
        ipmitool \
        iproute \
        iptables \
        iputils \
        jq \
        nc \
        net-tools \
        netperf \
        nftables \
        pciutils \
        procps-ng \
        python3 \
        python3.11 \
        sysstat \
        tcpdump \
        tini \
        util-linux \
        vim \
        wget \
        -y


RUN python3.11 -m venv /opt/pyvenv3.11
RUN /opt/pyvenv3.11/bin/python -m pip install --upgrade pip
RUN /opt/pyvenv3.11/bin/python -m pip install \
        pytest
COPY requirements.txt /tmp/
RUN /opt/pyvenv3.11/bin/python -m pip install -r /tmp/requirements.txt && \
    rm -rf /tmp/requirements.txt
RUN \
    echo -e "#/bin/sh\nexec /opt/pyvenv3.11/bin/python \"\$@\"" > /usr/bin/python-pyvenv3.11 && \
    chmod +x /usr/bin/python-pyvenv3.11 && \
    echo -e "#!/bin/sh\nexec /opt/pyvenv3.11/bin/python -m ktoolbox.netdev \"\$@\"" > /usr/bin/ktoolbox-netdev && \
    chmod +x /usr/bin/ktoolbox-netdev

RUN mkdir -p /etc/kubernetes-traffic-flow-tests && echo "kubernetes-traffic-flow-tests" > /etc/kubernetes-traffic-flow-tests/data

COPY ./scripts/simple-tcp-server-client.py /usr/bin/simple-tcp-server-client

COPY ./images/container-entry-point.sh /usr/bin/container-entry-point.sh

WORKDIR /
ENTRYPOINT ["/usr/bin/container-entry-point.sh"]
CMD ["/usr/bin/sleep", "infinity"]
