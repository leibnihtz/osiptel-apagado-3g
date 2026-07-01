import logging
from pathlib import Path


def setup_logging(log_dir: str | None = None) -> None:
    """
    Configura logging basico:
    - INFO en consola
    - opcionalmente INFO en archivo
    """
    handlers = [logging.StreamHandler()]

    if log_dir is not None:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.FileHandler(Path(log_dir) / "portalosiptel3g.log", encoding="utf-8")
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=handlers,
    )
