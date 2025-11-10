FROM bde2020/hadoop-base:2.0.0-hadoop3.2.1-java8

ARG PIG_VERSION=0.17.0
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl python2; \
    curl -fsSL "https://downloads.apache.org/pig/pig-${PIG_VERSION}/pig-${PIG_VERSION}.tar.gz" -o /tmp/pig.tar.gz; \
    mkdir -p /opt; \
    tar -xzf /tmp/pig.tar.gz -C /opt; \
    ln -s /opt/pig-${PIG_VERSION} /opt/pig; \
    rm -rf /tmp/pig.tar.gz /var/lib/apt/lists/*

ENV PIG_HOME=/opt/pig \
    PATH="$PATH:/opt/pig/bin"

COPY core-site.xml /opt/hadoop/etc/hadoop/core-site.xml
COPY hdfs-site.xml /opt/hadoop/etc/hadoop/hdfs-site.xml
COPY yarn-site.xml /opt/hadoop/etc/hadoop/yarn-site.xml

WORKDIR /opt/pig/scripts
CMD ["sleep", "infinity"]
