#!/bin/zsh
# 本地测试运行：走 Clash 代理 + certifi 证书。
# 模型 key 直接读 .env（QWEN_API_KEY=阿里云百炼 key），不再指向本机 Ollama。
export SSL_CERT_FILE=/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages/certifi/cacert.pem
export HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897
python3 -m src.pipeline
