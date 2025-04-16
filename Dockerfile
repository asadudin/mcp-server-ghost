FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY . .

# Install dependencies directly
RUN pip install --upgrade pip && \
    pip install httpx>=0.28.1 mcp[cli]>=1.6.0 pyjwt>=2.10.1 requests>=2.32.3

EXPOSE 8053

ENTRYPOINT ["python", "ghost-mcp-server.py"]
CMD ["--transport=sse"]

