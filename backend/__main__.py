from __future__ import annotations

import os

import uvicorn

from config import settings


def main() -> None:
    host = os.getenv("HOST", settings.api.host)
    port = int(os.getenv("PORT", str(settings.api.port)))
    uvicorn.run(
        "backend.api:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
