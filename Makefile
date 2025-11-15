COMPOSE := docker compose -f distributed-batch-ling/deploy/docker-compose.yml
PIG_SCRIPTS := /opt/pig/scripts
LOG_DIR := distributed-batch-ling/logs
OUTPUT_DIR := distributed-batch-ling/ingestion/output
HDFS := /opt/hdfs_exec.sh

.PHONY: up down ps logs hdfs-init load-data run-batch run-yahoo run-llm run-compare fetch metrics clean-logs compare

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

hdfs-init:
	$(COMPOSE) exec -T namenode sh -c "$(HDFS) dfs -mkdir -p /data/input/yahoo /data/input/llm /data/output/yahoo /data/output/llm /data/output/compare"

load-data: $(OUTPUT_DIR)/yahoo_respuestas.txt $(OUTPUT_DIR)/llm_respuestas.txt
	$(COMPOSE) cp $(OUTPUT_DIR)/yahoo_respuestas.txt namenode:/tmp/yahoo_respuestas.txt
	$(COMPOSE) cp $(OUTPUT_DIR)/llm_respuestas.txt namenode:/tmp/llm_respuestas.txt
	$(COMPOSE) exec -T namenode sh -c "$(HDFS) dfs -mkdir -p /data/input/yahoo /data/input/llm"
	$(COMPOSE) exec -T namenode sh -c "$(HDFS) dfs -put -f /tmp/yahoo_respuestas.txt /data/input/yahoo/"
	$(COMPOSE) exec -T namenode sh -c "$(HDFS) dfs -put -f /tmp/llm_respuestas.txt /data/input/llm/"

$(OUTPUT_DIR)/yahoo_respuestas.txt $(OUTPUT_DIR)/llm_respuestas.txt $(OUTPUT_DIR)/yahoo_respuestas.csv $(OUTPUT_DIR)/llm_respuestas.csv:
	@if [ -z "$(DUMP_PATH)" ]; then \
	        printf 'DUMP_PATH variable is required. Example: make load-data DUMP_PATH=data/respuestas.csv\n'; \
	        exit 1; \
	fi
	python distributed-batch-ling/ingestion/exporter.py --input $(DUMP_PATH) --output-dir $(OUTPUT_DIR) $(if $(VERBOSE),--verbose,)

run-batch: run-yahoo run-llm run-compare

run-yahoo:
	mkdir -p $(LOG_DIR) $(LOG_DIR)/pig
	$(COMPOSE) exec -T pig bash -lc "set -o pipefail && /opt/pig/bin/pig -x mapreduce -param INPUT=/data/input/yahoo/yahoo_respuestas.txt -param OUTPUT=/data/output/yahoo -param STOPWORDS=/opt/pig/scripts/stopwords_es.txt -param TOPN=50 -f /opt/pig/scripts/wordfreq.pig 2>&1 | tee /opt/pig/logs/pig_yahoo.log"
	@cat $(LOG_DIR)/pig/pig_yahoo.log > $(LOG_DIR)/pig_yahoo.log

run-llm:
	mkdir -p $(LOG_DIR) $(LOG_DIR)/pig
	$(COMPOSE) exec -T pig bash -lc "set -o pipefail && /opt/pig/bin/pig -x mapreduce -param INPUT=/data/input/llm/llm_respuestas.txt -param OUTPUT=/data/output/llm -param STOPWORDS=/opt/pig/scripts/stopwords_es.txt -param TOPN=50 -f /opt/pig/scripts/wordfreq.pig 2>&1 | tee /opt/pig/logs/pig_llm.log"
	@cat $(LOG_DIR)/pig/pig_llm.log > $(LOG_DIR)/pig_llm.log

run-compare:
	mkdir -p $(LOG_DIR) $(LOG_DIR)/pig
	$(COMPOSE) exec -T pig bash -lc "set -o pipefail && /opt/pig/bin/pig -x mapreduce -param INPUT_YAHOO=/data/output/yahoo/full -param INPUT_LLM=/data/output/llm/full -param OUTPUT=/data/output/compare/wordcount_diff -f /opt/pig/scripts/compare.pig 2>&1 | tee /opt/pig/logs/pig_compare.log"
	@cat $(LOG_DIR)/pig/pig_compare.log > $(LOG_DIR)/pig_compare.log

fetch:
	mkdir -p distributed-batch-ling/artifacts
	$(COMPOSE) exec -T namenode sh -c "rm -rf /tmp/batch-artifacts && mkdir -p /tmp/batch-artifacts && $(HDFS) dfs -get -f /data/output /tmp/batch-artifacts/"
	rm -rf distributed-batch-ling/artifacts/output
	$(COMPOSE) cp namenode:/tmp/batch-artifacts/data/output distributed-batch-ling/artifacts
	$(COMPOSE) exec -T namenode sh -c "rm -rf /tmp/batch-artifacts"

metrics:
	python distributed-batch-ling/scripts/metrics.py --compose-file distributed-batch-ling/deploy/docker-compose.yml

compare:
	python distributed-batch-ling/scripts/compare_topn.py --input-dir distributed-batch-ling/artifacts/output --output-dir distributed-batch-ling/artifacts $(if $(TOPN),--top-n $(TOPN),) $(if $(CHART),--chart,)
