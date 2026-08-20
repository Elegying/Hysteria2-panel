ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}

ENV container=docker
RUN if command -v apt-get >/dev/null 2>&1; then \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        dbus gawk systemd systemd-sysv util-linux && \
      rm -rf /var/lib/apt/lists/*; \
    else \
      dnf install -y dbus gawk systemd util-linux && dnf clean all; \
    fi

STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
