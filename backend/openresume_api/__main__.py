import uvicorn

from .config import settings


def main() -> None:
    uvicorn.run(
        "openresume_api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        factory=False,
    )


if __name__ == "__main__":
    main()

