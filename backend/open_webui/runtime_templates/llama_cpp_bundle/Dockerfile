FROM python:3.12-slim

WORKDIR /app

# Keep runtime inputs explicit so the generated bundle is reproducible and easy to audit.
ENV MODEL_PATH={{MODEL_PATH}}
ENV MEMORY_FLAG={{MEMORY_FLAG}}

COPY config.json /app/config.json
COPY template/ /app/template/

RUN pip install --no-cache-dir llama-cpp-python fastapi uvicorn

EXPOSE 8080

CMD ["sh", "-c", "python -m uvicorn template.app:app --host 0.0.0.0 --port 8080"]
