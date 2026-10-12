FROM python:3.11-slim

WORKDIR /srv
ENV PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/srv/models

# Install dependencies first, so code changes don't trigger a full reinstall
COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

# Download the embedding model at build time, so the container starts without internet
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

COPY app/ app/
COPY data/products.jsonl data/products.jsonl

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]