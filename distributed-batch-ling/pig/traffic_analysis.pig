REGISTER /opt/pig/udf/text_utils.py USING jython AS text_utils;

%default POLICY "unknown"
%default DISTRIBUTION "unknown"
%default INPUT "/data/in/traffic/unknown.csv"
%default OUTPUT "/data/out/traffic/unknown"

RAW = LOAD '$INPUT' USING PigStorage(',') AS (
    timestamp_iso:chararray,
    operation:chararray,
    message_id:chararray,
    question_id:chararray,
    status:chararray,
    latency_seconds:double,
    topic:chararray,
    policy:chararray,
    distribution:chararray,
    is_hit:int,
    was_evicted:int
);

WITH_META = FOREACH RAW GENERATE
    timestamp_iso,
    operation,
    message_id,
    question_id,
    status,
    latency_seconds,
    (topic is not null ? topic : 'unknown') AS topic:chararray,
    (policy is not null ? policy : '$POLICY') AS policy:chararray,
    (distribution is not null ? distribution : '$DISTRIBUTION') AS distribution:chararray,
    (is_hit is not null ? is_hit : 0) AS is_hit:int,
    (was_evicted is not null ? was_evicted : 0) AS was_evicted:int;

GRP_ALL = GROUP WITH_META ALL;
STATS_GLOBAL = FOREACH GRP_ALL {
    total = COUNT(WITH_META);
    hits = SUM(WITH_META.is_hit);
    evictions = SUM(WITH_META.was_evicted);
    hit_ratio = (total == 0 ? 0.0 : (double)hits / (double)total);
    eviction_ratio = (total == 0 ? 0.0 : (double)evictions / (double)total);
    GENERATE
        '$POLICY' AS policy:chararray,
        '$DISTRIBUTION' AS distribution:chararray,
        total AS total_requests:long,
        hits AS total_hits:long,
        evictions AS total_evictions:long,
        hit_ratio AS hit_ratio:double,
        eviction_ratio AS eviction_ratio:double,
        AVG(WITH_META.latency_seconds) AS avg_latency_seconds:double,
        MIN(WITH_META.latency_seconds) AS min_latency_seconds:double,
        MAX(WITH_META.latency_seconds) AS max_latency_seconds:double;
};

BY_TOPIC = GROUP WITH_META BY topic;
STATS_BY_TOPIC = FOREACH BY_TOPIC {
    total = COUNT(WITH_META);
    hits = SUM(WITH_META.is_hit);
    evictions = SUM(WITH_META.was_evicted);
    GENERATE
        '$POLICY' AS policy:chararray,
        '$DISTRIBUTION' AS distribution:chararray,
        group AS topic:chararray,
        total AS total_requests:long,
        hits AS total_hits:long,
        evictions AS total_evictions:long,
        (total == 0 ? 0.0 : (double)hits / (double)total) AS hit_ratio:double,
        AVG(WITH_META.latency_seconds) AS avg_latency_seconds:double;
};

BY_STATUS = GROUP WITH_META BY status;
STATS_BY_STATUS = FOREACH BY_STATUS {
    total = COUNT(WITH_META);
    hits = SUM(WITH_META.is_hit);
    evictions = SUM(WITH_META.was_evicted);
    GENERATE
        '$POLICY' AS policy:chararray,
        '$DISTRIBUTION' AS distribution:chararray,
        group AS status:chararray,
        total AS total_requests:long,
        hits AS total_hits:long,
        evictions AS total_evictions:long,
        (total == 0 ? 0.0 : (double)hits / (double)total) AS hit_ratio:double,
        AVG(WITH_META.latency_seconds) AS avg_latency_seconds:double;
};

STORE STATS_GLOBAL INTO '$OUTPUT/stats_global_${POLICY}_${DISTRIBUTION}' USING PigStorage('\t');
STORE STATS_BY_TOPIC INTO '$OUTPUT/stats_by_topic_${POLICY}_${DISTRIBUTION}' USING PigStorage('\t');
STORE STATS_BY_STATUS INTO '$OUTPUT/stats_by_status_${POLICY}_${DISTRIBUTION}' USING PigStorage('\t');
