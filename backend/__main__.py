from __future__ import annotations

import uvicorn

from config import settings


def main() -> None:
    uvicorn.run(
        "backend.api:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
