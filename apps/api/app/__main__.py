from __future__ import annotations

import uvicorn

from app.settings import get_config


def main() -> None:
    config = get_config()
    uvicorn.run("app.main:app", host=config.api.host, port=config.api.port)


if __name__ == "__main__":
    main()
