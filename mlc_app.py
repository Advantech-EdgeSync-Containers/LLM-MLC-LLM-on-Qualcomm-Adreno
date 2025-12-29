import os
import re
import asyncio
import shlex
import time

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

# -------------------------------
# Env Vars
# -------------------------------
MODEL_PATH = os.environ.get("MLC_MODEL_PATH", "")
MODEL_LIB = os.environ.get("MODEL_LIB", "")
MLC_DEVICE = os.environ.get("MLC_DEVICE", "opencl")
MODEL_NAME = os.environ.get("MLC_MODEL_NAME", "MLC_LLM_Model")
CLI_BIN = os.environ.get("MLC_CLI_BIN", "/workspace/mlc-llm/build/apps/mlc_cli_chat/mlc_cli_chat")
TIMEOUT = int(os.environ.get("MLC_TIMEOUT", "20")) * 60  # default 1 minute

# -------------------------------
# FastAPI app
# -------------------------------
app = FastAPI()


# -------------------------------
# Helper: run CLI and stream token-by-token, preserving newlines
# -------------------------------
import shlex, time, re, asyncio


def sanitize_prompt(text: str) -> str:
    """
    Sanitize a prompt for safe CLI use with --with-prompt.
    - Removes newlines and carriage returns
    - Strips dangerous quotes/backticks
    - Collapses multiple spaces
    - Keeps meaningful math symbols (*, ^, |, /, π, <, >, =)
    """
    # Remove newlines and carriage returns
    text = text.replace("\n", " ").replace("\r", " ")

    # Remove quotes/backticks that can break shell
    text = re.sub(r"[\"'`]", "", text)

    # Allow only safe characters (letters, numbers, spaces, punctuation, math symbols)
    text = re.sub(r"[^a-zA-Z0-9\s\*\^\|\(\)\[\]\{\}\/\+\-\=\.:\?,π<>]", "", text)

    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()

    return text


async def run_cli(prompt: str):

    cmd = [
        CLI_BIN,
        "--model", MODEL_PATH,
        "--model-lib", MODEL_LIB,
        "--device", MLC_DEVICE,
        "--with-prompt", shlex.quote(sanitize_prompt(prompt)),
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    start_time = time.monotonic()
    deadline = start_time + TIMEOUT

    comma_count = 0

    buf = ""
    capturing = False

    try:
        while True:
            chunk = await process.stdout.read(64)  # read a bit more than 1 byte
            if not chunk:
                break

            # timeout check
            if time.monotonic() >= deadline:
                if process.returncode is None:
                    process.kill()
                yield f"data: {{\"error\":\"Process killed after {TIMEOUT}s timeout.\"}}\n\n"
                break


            line = chunk.decode("utf-8", errors="ignore")
            if '"""' in line or '""' in line:
                comma_count += 1

            buf += line

            if not capturing and comma_count > 1:
                capturing = True

            if capturing and 'decode :' in line:
                capturing = False
                comma_count = 0

            if not capturing:
                continue

            for word in re.findall(r"\S+|\s", line):
                token = "\\n" if word == "\n" else word
                await asyncio.sleep(0.05)

                yield (
                    f"data: {{\"id\":\"chatcmpl-temp\",\"object\":\"chat.completion.chunk\","
                    f"\"model\":\"{MODEL_NAME}\",\"choices\":[{{\"index\":0,"
                    f"\"delta\":{{\"content\":\"{token}\"}},\"finish_reason\":null}}]}}\n\n"
                )

    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()

    yield "data: [DONE]\n\n"

# -------------------------------
# Endpoint: /v1/models
# -------------------------------
@app.get("/v1/models")
async def list_models():
    return {"data": [{"id": MODEL_NAME, "object": "model"}]}


# -------------------------------
# Endpoint: /v1/chat/completions
# -------------------------------
@app.post("/v1/chat/completions")
async def chat_completions(body: dict):
    prompt = body["messages"][-1]["content"]

    return StreamingResponse(
        run_cli(prompt),
        media_type="text/event-stream",
    )
