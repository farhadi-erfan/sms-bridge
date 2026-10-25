FROM python:3.12-slim
WORKDIR /app
COPY web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -r -u 10001 app && mkdir /data && chown app /data
COPY --chown=app:app web/ .
USER 10001:10001
ENV DATABASE_PATH=/data/inbox.sqlite
EXPOSE 8765
CMD ["gunicorn", "--bind", "0.0.0.0:8765", "--workers", "2", "--threads", "4", "--forwarded-allow-ips", "", "app:application"]
