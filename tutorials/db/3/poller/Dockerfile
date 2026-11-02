# Poller Worker Image
FROM python:3.9-slim

# Install Postgres Driver (psycopg2) and system deps
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

COPY poll.py /poll.py
CMD ["python", "/poll.py"]
