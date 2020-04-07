FROM python:3.8 as base

WORKDIR /app
COPY pip-tools/requirements.txt ./pip-tools/
RUN pip install -r pip-tools/requirements.txt

# ============================================
# ==  DEVELOPMENT                           ==
# ============================================
FROM base as dev

COPY pip-tools/dev-requirements.txt ./pip-tools/
RUN pip install -r pip-tools/dev-requirements.txt

COPY . .

CMD ["pytest"]

# ============================================
# ==  PRODUCTION                            ==
# ============================================
FROM base as prod

COPY . .

EXPOSE 8000
CMD ["gunicorn", "-b", "0.0.0.0:8000", "broker:create_app"]

