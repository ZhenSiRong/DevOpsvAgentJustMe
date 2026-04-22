#!/bin/bash
# DevOps Agent DB Repository 测试运行脚本
cd /root/devops-agent
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
python3 -m pytest tests/test_db_repos.py -v --tb=short > /tmp/pt_latest.txt 2>&1
echo "EXIT_CODE=$?" >> /tmp/pt_latest.txt
