# Build image
FROM python:3.12-slim-bookworm as build

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /usr/src/app

RUN apt update && apt install --no-install-recommends -y \
    git-core \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev

COPY ./requirements.txt .

# Install python requirements, collect as wheels and re-install
# later on in the `production` stage
RUN pip install --upgrade pip && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /usr/src/app/wheels -r requirements.txt

# ------------------------------------------------------------------------------
# Production image
FROM python:3.12-slim-bookworm

ENV PYTHONPATH /ksicht
ENV DJANGO_SETTINGS_MODULE ksicht.settings
ENV PATH "/ksicht/.local/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Create custom user to avoid running as a root
RUN mkdir -p /ksicht && \
    addgroup --gid 990 ksicht && \
    useradd -u 994 -g ksicht -d /ksicht ksicht && \
    chown ksicht:ksicht /ksicht && \
    # Install dependencies
    apt update && apt install --no-install-recommends -y \
    nginx \
    supervisor && \
    mkdir -p /run/nginx

# Supervisor and Nginx configs
COPY ./docker/supervisor.conf /etc/supervisor/conf.d/supervisor.conf
COPY ./docker/nginx.conf /etc/nginx/nginx.conf

COPY --from=build /usr/src/app/wheels /wheels
COPY --from=build /usr/src/app/requirements.txt .

USER ksicht
WORKDIR /ksicht

# Install requirements under user priviledges
RUN pip install --upgrade pip && \
    pip install --user --no-cache /wheels/* && \
    rm -rf /ksicht/.cache/pip

COPY --chown=ksicht docker/entrypoint.sh /ksicht/
COPY --chown=ksicht webpack-stats.json /ksicht/
COPY --chown=ksicht ./assets /ksicht/assets
COPY --chown=ksicht ./ksicht ./ksicht/
COPY --chown=ksicht ./fonts ./fonts/
COPY --chown=ksicht ./fixtures ./fixtures/

# Collect static files
RUN mkdir -p /ksicht/static && \
    SECRET_KEY=x DEBUG=1 django-admin collectstatic --noinput --verbosity=0

USER root

# Prepare media directory
RUN mkdir -p /media && \
    chown ksicht:ksicht /media && \
    # Drop wheels, not needed anymore
    rm -rf /wheels

EXPOSE 8080

CMD ["sh", "./entrypoint.sh"]
