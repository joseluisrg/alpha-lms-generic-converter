# syntax=docker/dockerfile:1.7

FROM python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS builder

ARG UV_VERSION=0.13.6

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /src

RUN python -m pip install --no-cache-dir --disable-pip-version-check "uv==${UV_VERSION}"

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY adapters ./adapters
COPY cli ./cli
COPY core ./core
COPY domain ./domain
COPY persistence ./persistence
COPY streamlit_app.py ./

RUN uv export --quiet --frozen --no-dev --extra ui --no-emit-project --output-file /tmp/requirements.txt \
    && uv build --wheel --out-dir /tmp/dist

FROM python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS runtime

LABEL org.opencontainers.image.title="LMS Converter" \
      org.opencontainers.image.description="Vendor-neutral course migration between Moodle and Open edX" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/olgakazarina-guds/Team-Delta"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    LMS_CONVERTER_DATA_DIR=/app/data \
    LMS_CONVERTER_ENV=production \
    LMS_CONVERTER_AUTH_MODE=proxy \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home \
        --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /app/data \
    && chown app:app /app/data \
    && chmod 0750 /app/data

WORKDIR /app

COPY --from=builder /tmp/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --no-compile --require-hashes \
        -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

COPY --from=builder /tmp/dist/*.whl /tmp/wheels/
RUN python -m pip install --no-cache-dir --no-compile --no-deps /tmp/wheels/*.whl \
    && rm -rf /tmp/wheels

COPY --chown=root:root streamlit_app.py /app/streamlit_app.py
COPY --chown=root:root LICENSE /usr/share/licenses/lms-converter/LICENSE

USER 10001:10001

EXPOSE 8501

STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3).read()"]

CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
