FROM python:3.8-slim as base

RUN useradd -m --no-log-init app
ENV PATH=/usr/local/bin:/usr/lib/postgresql/11/bin:$PATH

WORKDIR /app

# ============================================
# ==  DEVELOPMENT                           ==
# ============================================
FROM base as dev

ENV TINI_VERSION v0.18.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini
RUN chmod +x /tini

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
                    postgresql-common \
                    postgresql

RUN chown -R app:app /var/lib/postgresql
RUN chown -R app:app /var/run/postgresql

COPY pip-tools/dev-requirements.txt ./pip-tools/
RUN pip install -r pip-tools/dev-requirements.txt

COPY . .

USER app

ENTRYPOINT ["/app/docker/entrypoint-dev.sh"]
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

