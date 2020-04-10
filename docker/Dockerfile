FROM python:3.8-slim as base

WORKDIR /app

# ============================================
# ==  DEVELOPMENT                           ==
# ============================================
FROM base as dev

ENV TINI_VERSION v0.18.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini
RUN chmod +x /tini

COPY pip-tools/dev-requirements.txt ./pip-tools/
RUN pip install -r pip-tools/dev-requirements.txt

COPY . .

RUN useradd -m --no-log-init app
USER app
ENV PATH=/usr/local/bin:$PATH

CMD ["docker/run_tests"]

# ============================================
# ==  PRODUCTION                            ==
# ============================================
FROM base as prod

COPY pip-tools/requirements.txt ./pip-tools/
RUN pip install -r pip-tools/requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000
CMD ["bash", "-c", "gunicorn -b 0.0.0.0:$PORT 'broker:create_app()'"]

