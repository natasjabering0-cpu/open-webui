#!/bin/bash
set -e
MODEL_PATH="${1:-missing}"
PORT="${2:-3000}"
CONTEXT="${3:-4096}"
THREADS="${4:-4}"

if [[ "$MODEL_PATH" == "missing" ]]; then
    echo "Usage: deploy-minimal.sh <model.gguf> [port] [context] [threads]"
    echo "Example: deploy-minimal.sh mistral-7b.Q4_K_M.gguf 3000"
    exit 1
fi

[[ ! -f "$MODEL_PATH" ]] && echo "Model not found: $MODEL_PATH" && exit 1
MODEL_NAME=$(basename "$MODEL_PATH")

cat > Dockerfile.min <<EOF
FROM ghcr.io/open-webui/open-webui:main
RUN pip install llama-cpp-python==0.2.90
COPY "$MODEL_PATH" /models/
ENV LLAMA_MODEL_PATH=/models/$MODEL_NAME
ENV LLAMA_CONTEXT_SIZE=$CONTEXT
ENV LLAMA_THREADS=$THREADS
EXPOSE $PORT
CMD ["pip","start"]
EOF

docker build -f Dockerfile.min -t owui-min:latest --build-context .=. .
rm Dockerfile.min
docker run -d -p $PORT:8080 -v owi-data:/app/backend/data --name owui-min --restart always owui-min:latest
echo "http://localhost:$PORT - Ready!"