FROM bde2020/hadoop-base:2.0.0-hadoop3.2.1-java8

ARG PIG_VERSION=0.17.0
RUN set -eux; \
    printf '%s\n' \
        'deb http://archive.debian.org/debian stretch main' \
        'deb http://archive.debian.org/debian stretch contrib non-free' \
        > /etc/apt/sources.list; \
    printf 'Acquire::Check-Valid-Until "false";\nAcquire::AllowInsecureRepositories "true";\n' > /etc/apt/apt.conf.d/99archive; \
    apt-get update; \
    apt-get install -y --no-install-recommends bash curl python; \
    curl -fsSL "https://downloads.apache.org/pig/pig-${PIG_VERSION}/pig-${PIG_VERSION}.tar.gz" -o /tmp/pig.tar.gz; \
    mkdir -p /opt; \
    tar -xzf /tmp/pig.tar.gz -C /opt; \
    ln -s /opt/pig-${PIG_VERSION} /opt/pig; \
    rm -rf /tmp/pig.tar.gz /var/lib/apt/lists/*

ENV PIG_HOME=/opt/pig \
    PATH="$PATH:/opt/pig/bin"

COPY deploy/hadoop/core-site.xml /opt/hadoop/etc/hadoop/core-site.xml
COPY deploy/hadoop/hdfs-site.xml /opt/hadoop/etc/hadoop/hdfs-site.xml
COPY deploy/hadoop/yarn-site.xml /opt/hadoop/etc/hadoop/yarn-site.xml

WORKDIR /opt/pig/scripts
CMD ["sleep", "infinity"]
