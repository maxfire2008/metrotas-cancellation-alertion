# syntax=docker/dockerfile:1

FROM python:3.11-slim

LABEL org.opencontainers.image.source https://github.com/maxfire2008/metrotas-cancellation-alertion

ENV TZ="Australia/Hobart"

WORKDIR /app

RUN pip3 install poetry

COPY pyproject.toml /app
COPY poetry.lock /app

RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi

COPY . /app

CMD [ "python3", "discord_bot.py", "${TOKEN}" ]