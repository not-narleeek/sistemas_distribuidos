ROOT_DIR := ..

.PHONY: up down ps logs hdfs-init load-data run-batch run-yahoo run-llm run-compare fetch metrics clean-logs

up:
	$(MAKE) -C $(ROOT_DIR) up

down:
	$(MAKE) -C $(ROOT_DIR) down

ps:
	$(MAKE) -C $(ROOT_DIR) ps

logs:
	$(MAKE) -C $(ROOT_DIR) logs

hdfs-init:
	$(MAKE) -C $(ROOT_DIR) hdfs-init

load-data:
	$(MAKE) -C $(ROOT_DIR) load-data

run-batch:
	$(MAKE) -C $(ROOT_DIR) run-batch

run-yahoo:
	$(MAKE) -C $(ROOT_DIR) run-yahoo

run-llm:
	$(MAKE) -C $(ROOT_DIR) run-llm

run-compare:
	$(MAKE) -C $(ROOT_DIR) run-compare

fetch:
	$(MAKE) -C $(ROOT_DIR) fetch

metrics:
	$(MAKE) -C $(ROOT_DIR) metrics

clean-logs:
	$(MAKE) -C $(ROOT_DIR) clean-logs
