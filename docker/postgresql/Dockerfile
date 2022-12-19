FROM postgres:11

ARG UID=2000
ARG GID=2000
ARG USER=pg-user

RUN grep -q ":$GID:" /etc/group \
 || groupadd --gid="$GID" "$USER"

RUN useradd \
      --home-dir="/home/$USER" \
      --no-log-init \
      --create-home \
      --shell=/bin/bash \
      --gid=$GID \
      --uid=$UID \
      --no-user-group \
      --non-unique \
      "$USER"
      
ENV PGDATA /tmp/data
ENV PGCONFIG /tmp/data/postgresql.conf
ENV PATH="$PATH:/usr/lib/postgresql/$PG_MAJOR/bin"
ENV POSTGRES_HOST_AUTH_METHOD=trust

RUN mkdir -p "$PGDATA" \
 && chown -R "$USER:" "$PGDATA" \
 && chmod 700 "$PGDATA"

USER $UID:$GID

RUN initdb \
  && echo "unix_socket_directories = '$PGDATA'" >> "$PGCONFIG" \
  && echo "log_statement = 'all'" >> "$PGCONFIG" \
  && echo "log_connections = on" >> "$PGCONFIG" \
  && echo "log_disconnections = on" >> "$PGCONFIG" \
  && echo "log_line_prefix = ''" >> "$PGCONFIG" \
  && sed -ri "s!^#?(listen_addresses)\s*=\s*\S+.*!\1 = '*'!" "$PGCONFIG" \
  && grep -F "listen_addresses = '*'" "$PGCONFIG" \
  && echo 'CREATE DATABASE "test"' | postgres --single -D "$PGDATA" postgres \
  && echo 'CREATE DATABASE "local-development"' | postgres --single -D "$PGDATA" postgres