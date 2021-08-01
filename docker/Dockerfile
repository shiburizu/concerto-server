FROM python:3.8.11-alpine3.14

COPY requirements.txt requirements.txt

# Taken from https://stackoverflow.com/a/47871121, problems due to psycopg2
RUN \
 apk add --no-cache postgresql-libs && \
 apk add --no-cache --virtual .build-deps gcc g++ musl-dev postgresql-dev && \
 python3 -m pip install -r requirements.txt --no-cache-dir && \
 apk --purge del .build-deps

COPY . .

CMD ["gunicorn", "-w", "4", "main:app"]