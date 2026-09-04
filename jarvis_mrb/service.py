from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

from jarvis_mrb.agent import handle_natural_language


app = FastAPI(title="Jarvis for MRB", version="0.2.0")


class CommandRequest(BaseModel):
    text: str


class CommandResponse(BaseModel):
    ok: bool
    message: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/command", response_model=CommandResponse)
def command(request: CommandRequest) -> CommandResponse:
    reply = handle_natural_language(request.text)
    return CommandResponse(ok=reply.ok, message=reply.message)


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")


if __name__ == "__main__":
    main()
