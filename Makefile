COMPOSE := docker compose -f distributed-batch-ling/deploy/docker-compose.yml
PIG_SCRIPTS := /opt/pig/scripts
LOG_DIR := distributed-batch-ling/logs
OUTPUT_DIR := distributed-batch-ling/ingestion/output
HADOOP_PATH := /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/hadoop/bin:/opt/hadoop-3.2.1/bin
HADOOP_PATH_EXPORT := PATH=$(HADOOP_PATH)
HDFS := $(HADOOP_PATH_EXPORT) hdfs

.PHONY: up down ps logs ensure-bash hdfs-init load-data run-batch run-yahoo run-llm run-compare fetch metrics clean-logs

up:
	$(COMPOSE) up -d --build

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f

down:
	$(COMPOSE) down

clean-logs:
	rm -f $(LOG_DIR)/*.log $(LOG_DIR)/pig/*.log

ensure-bash:
	$(COMPOSE) exec -T namenode sh -lc 'if command -v bash >/dev/null 2>&1; then exit 0; fi; if ! command -v apt-get >/dev/null 2>&1; then echo >&2 "bash is required but apt-get is not available to install it"; exit 127; fi; if [ -w /etc/apt/sources.list ]; then printf "%s\n" "deb http://archive.debian.org/debian stretch main" "deb http://archive.debian.org/debian stretch contrib non-free" > /etc/apt/sources.list; printf "Acquire::Check-Valid-Until \"false\";\nAcquire::AllowInsecureRepositories \"true\";\n" > /etc/apt/apt.conf.d/99archive; fi; apt-get update; apt-get install -y --no-install-recommends bash; rm -rf /var/lib/apt/lists/*'

hdfs-init: ensure-bash
	$(COMPOSE) exec -T namenode sh -lc "$(HDFS) dfs -mkdir -p /data/input/yahoo /data/input/llm /data/output/yahoo /data/output/llm /data/output/compare"

load-data: ensure-bash $(OUTPUT_DIR)/yahoo_respuestas.csv $(OUTPUT_DIR)/llm_respuestas.csv
	$(COMPOSE) cp $(OUTPUT_DIR)/yahoo_respuestas.csv namenode:/tmp/yahoo_respuestas.csv
	$(COMPOSE) cp $(OUTPUT_DIR)/llm_respuestas.csv namenode:/tmp/llm_respuestas.csv
	$(COMPOSE) exec -T namenode sh -lc "$(HDFS) dfs -mkdir -p /data/input/yahoo /data/input/llm"
	$(COMPOSE) exec -T namenode sh -lc "$(HDFS) dfs -put -f /tmp/yahoo_respuestas.csv /data/input/yahoo/"
	$(COMPOSE) exec -T namenode sh -lc "$(HDFS) dfs -put -f /tmp/llm_respuestas.csv /data/input/llm/"

$(OUTPUT_DIR)/yahoo_respuestas.csv $(OUTPUT_DIR)/llm_respuestas.csv:
	@if [ -z "$(DUMP_PATH)" ]; then \
		printf 'DUMP_PATH variable is required. Example: make load-data DUMP_PATH=data/respuestas.csv\n'; \
		exit 1; \
	fi
	python distributed-batch-ling/ingestion/exporter.py --input $(DUMP_PATH) --output-dir $(OUTPUT_DIR) $(if $(VERBOSE),--verbose,)

run-batch: run-yahoo run-llm run-compare

run-yahoo:
	mkdir -p $(LOG_DIR) $(LOG_DIR)/pig
	$(COMPOSE) exec -T pig bash -lc "set -o pipefail && pig -x mapreduce -param INPUT=/data/input/yahoo -param OUTPUT=/data/output/yahoo/wordcount -param TOP_OUTPUT=/data/output/yahoo/top50 -param STOPWORDS=/opt/pig/scripts/stopwords_es.txt -f /opt/pig/scripts/wordcount_yahoo.pig 2>&1 | tee /opt/pig/logs/pig_yahoo.log"
	@cat $(LOG_DIR)/pig/pig_yahoo.log > $(LOG_DIR)/pig_yahoo.log

run-llm:
	mkdir -p $(LOG_DIR) $(LOG_DIR)/pig
	$(COMPOSE) exec -T pig bash -lc "set -o pipefail && pig -x mapreduce -param INPUT=/data/input/llm -param OUTPUT=/data/output/llm/wordcount -param TOP_OUTPUT=/data/output/llm/top50 -param STOPWORDS=/opt/pig/scripts/stopwords_es.txt -f /opt/pig/scripts/wordcount_llm.pig 2>&1 | tee /opt/pig/logs/pig_llm.log"
	@cat $(LOG_DIR)/pig/pig_llm.log > $(LOG_DIR)/pig_llm.log

run-compare:
	mkdir -p $(LOG_DIR) $(LOG_DIR)/pig
	$(COMPOSE) exec -T pig bash -lc "set -o pipefail && pig -x mapreduce -param INPUT_YAHOO=/data/output/yahoo/wordcount -param INPUT_LLM=/data/output/llm/wordcount -param OUTPUT=/data/output/compare/wordcount_diff -f /opt/pig/scripts/compare.pig 2>&1 | tee /opt/pig/logs/pig_compare.log"
	@cat $(LOG_DIR)/pig/pig_compare.log > $(LOG_DIR)/pig_compare.log

fetch: ensure-bash
	mkdir -p distributed-batch-ling/artifacts
	$(COMPOSE) exec -T namenode sh -lc "rm -rf /tmp/batch-artifacts && mkdir -p /tmp/batch-artifacts && $(HDFS) dfs -get -f /data/output /tmp/batch-artifacts/"
	rm -rf distributed-batch-ling/artifacts/output
	$(COMPOSE) cp namenode:/tmp/batch-artifacts/data/output distributed-batch-ling/artifacts
	$(COMPOSE) exec -T namenode sh -lc "rm -rf /tmp/batch-artifacts"

metrics:
	python distributed-batch-ling/scripts/metrics.py --compose-file distributed-batch-ling/deploy/docker-compose.yml
