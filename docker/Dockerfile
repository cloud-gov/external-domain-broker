FROM python:3.8-slim as base

RUN useradd -m --no-log-init app
ENV PATH=/usr/local/bin:/usr/lib/postgresql/11/bin:$PATH
ENV FLASK_APP="broker:create_app()"

WORKDIR /app

# ============================================
# ==  DEVELOPMENT                           ==
# ============================================
FROM base as dev

RUN apt-get update && apt-get install -y --no-install-recommends curl

COPY pip-tools/dev-requirements.txt ./pip-tools/
RUN pip install -r pip-tools/dev-requirements.txt

# When building locally, these should be set to your UID/GID.  That way, any
# files written to the $PWD mount will be owned by you.  This is not
# necessary (or wanted) when building in Concourse.
ARG UID=2000
ARG GID=2000
ARG USER=app

RUN groupadd --gid=$GID $USER
RUN useradd \
      --home-dir=/home/$USER \
      --no-log-init \
      --create-home \
      --shell=/bin/bash \
      --gid=$GID \
      --uid=$UID \
      $USER

USER $USER:$USER

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

