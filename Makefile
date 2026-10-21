PYTHON ?= python3

.PHONY: help test fetch
help:
	@echo 'make test  - 验证 RSS 响应校验和旧文件保护'
	@echo 'make fetch - 抓取公开订阅源并写入 feeds/'

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'

fetch:
	$(PYTHON) scripts/fetch_feeds.py
