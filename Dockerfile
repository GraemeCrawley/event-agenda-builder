FROM python:3.12-slim
WORKDIR /srv/app
COPY requirements.txt /srv/
RUN pip install --no-cache-dir -r /srv/requirements.txt
COPY app/ /srv/app/
COPY tools/ /srv/tools/
# Built-in sample event, used when no EVENT_DIR is mounted.
COPY samples/ /srv/samples/
# Run as a normal user (uid 1000) so files the tools write into a mounted
# folder belong to you, not root.
RUN useradd -u 1000 -m app && mkdir /data && chown app /data
USER app
ENV EVENT_DIR=/srv/samples/example-event DATA_DIR=/data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
