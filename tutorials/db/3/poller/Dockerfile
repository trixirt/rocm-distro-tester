# Poller Worker Image
FROM python:3.9-slim

# Install Postgres Driver (psycopg2) and system deps
RUN pip install psycopg2-binary

COPY poll.py /poll.py
CMD ["python", "/poll.py"]
