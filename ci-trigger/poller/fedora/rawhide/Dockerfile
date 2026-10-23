# Plan compliance: §7.5.2 - Using pinned Fedora rawhide base for poller logic
FROM rocm-builder:5001/fedora-rawhide:rawhide

LABEL maintainer="rocm-tester@example.com"
LABEL description="Fedora RAWHIDE Poller Service (Fedora Base)"

COPY packages.txt /
COPY poll.sh /

CMD ["/poll.sh"]
