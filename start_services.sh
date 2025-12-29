#!/bin/bash
# Script to run MLC LLM server with OpenWebUI integration
set -e

# Load environment variables from .env file if present
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Initialize conda for bash shell
source "$(conda info --base)/etc/profile.d/conda.sh"

# Activate conda env
echo "Activating conda environment: mlc-venv"
conda activate mlc-venv

# Info log
echo "=========================================="
echo " Starting MLC LLM server"
echo "------------------------------------------"
echo "Model Name:    $OPENAI_MODEL_NAME"
echo "Model Path:    $MLC_MODEL_PATH"
echo "Model Lib:     $MODEL_LIB"
echo "Host:          $MLC_HOST"
echo "Port:          $MLC_PORT"
echo "Mode:          $MLC_MODE"
echo "=========================================="

# Run server
nohup uvicorn mlc_app:app --host $MLC_HOST --port $MLC_PORT > mlc_llm_uvicorn.log 2>&1 &
echo $! > mlc_llm_uvicorn.pid
echo "Mlc llm server started (PID: $(cat mlc_llm_uvicorn.pid))"
