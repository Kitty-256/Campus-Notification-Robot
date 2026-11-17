FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# WITH_BROWSER=1 时额外装 playwright + chromium（信息学院等 JS 渲染站点要用）
# 构建：docker compose build --build-arg WITH_BROWSER=1
# 代价：镜像大 ~400MB、构建慢几分钟；不装则 kind: browser 的源会被跳过
ARG WITH_BROWSER=0

COPY requirements.txt .
COPY requirements-browser.txt .
RUN pip install -r requirements.txt \
    && if [ "$WITH_BROWSER" = "1" ]; then \
         pip install -r requirements-browser.txt && playwright install --with-deps chromium; \
       fi

COPY schema.sql .
COPY app ./app
COPY config ./config

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
