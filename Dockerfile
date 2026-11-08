# 财税合规问答系统 — 一键部署镜像（零依赖）
# 构建：docker build -t finance-tax-compliance .
# 运行：docker run -d -p 8777:8777 finance-tax-compliance
FROM python:3.12-slim

LABEL org.opencontainers.image.title="finance-tax-compliance" \
      org.opencontainers.image.description="中国财税合规问答系统（确定性计算 + 可溯源 RAG）" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

# 零依赖：无需 requirements.txt；仅拷贝运行必需文件
COPY app/ /app/app/

EXPOSE 8777

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8777/api/health', timeout=4).status==200 else 1)"

CMD ["python", "app/server.py", "8777"]
