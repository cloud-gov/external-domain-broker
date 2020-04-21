FROM python:3.8-slim as base

RUN useradd -m --no-log-init app
ENV PATH=/usr/local/bin:/usr/lib/postgresql/11/bin:$PATH

WORKDIR /app

# ============================================
# ==  DEVELOPMENT                           ==
# ============================================
FROM base as dev

RUN apt-get update && apt-get install -y --no-install-recommends curl

COPY pip-tools/dev-requirements.txt ./pip-tools/
RUN pip install -r pip-tools/dev-requirements.txt

USER app

ENV FLASK_ENV=development

COPY . .

CMD ["docker/run_tests"]

# ============================================
# ==  PRODUCTION                            ==
# ============================================
FROM base as prod

COPY pip-tools/requirements.txt ./pip-tools/
RUN pip install -r pip-tools/requirements.txt

COPY . .

ENV FLASK_ENV=production
ENV PORT=8000
EXPOSE 8000
CMD ["bash", "-c", "gunicorn -b 0.0.0.0:$PORT 'broker:create_app()'"]

