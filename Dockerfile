FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md README_EN.md ./
COPY tg_signer ./tg_signer

RUN pip install --upgrade pip && \
    pip install --prefix=/install ".[gui,speedup]"


FROM python:3.12-slim

ARG TZ=Asia/Shanghai

ENV TZ=${TZ} \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TG_SIGNER_WORKDIR=/data/.signer \
    TG_SIGNER_SESSION_DIR=/data/sessions \
    TG_SIGNER_LOG_DIR=/data/logs \
    TG_SIGNER_LOG_FILE=/data/logs/tg-signer.log \
    TG_SIGNER_GUI_HOST=0.0.0.0 \
    TG_SIGNER_GUI_PORT=8080

RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
    ln -snf "/usr/share/zoneinfo/${TZ}" /etc/localtime && \
    echo "${TZ}" > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh && \
    mkdir -p /data/.signer /data/sessions /data/logs

WORKDIR /data

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
