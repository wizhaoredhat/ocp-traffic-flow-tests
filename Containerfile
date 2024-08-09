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
        PyYAML==6.0.1 \
        dataclasses \
        jc \
        jinja2 \
        pytest
RUN ln -s /opt/pyvenv3.11/bin/python /usr/bin/python-pyvenv3.11

COPY \
    ktoolbox/README.md \
    ktoolbox/*.py \
    /opt/ocp-tft/ktoolbox/

RUN echo -e "#!/bin/bash\ncd /opt/ocp-tft/ && exec /opt/pyvenv3.11/bin/python -m ktoolbox.netdev \"\$@\"" > /usr/bin/ocp-tft-netdev && chmod +x /usr/bin/ocp-tft-netdev

RUN mkdir -p /etc/ocp-traffic-flow-tests && echo "ocp-traffic-flow-tests" > /etc/ocp-traffic-flow-tests/data

COPY ./scripts/simple-tcp-server-client.py /usr/bin/simple-tcp-server-client

COPY ./images/container-entry-point.sh /usr/bin/container-entry-point.sh

ENTRYPOINT ["/usr/bin/container-entry-point.sh"]
CMD ["/usr/bin/sleep", "infinity"]
