from __future__ import annotations

import os

from addressforge.ingestion.service import run_default_ingestion


def main() -> None:
    batch_size = int(os.getenv("ADDRESSFORGE_INGESTION_BATCH_SIZE", "1000"))
    mode = os.getenv("ADDRESSFORGE_INGESTION_MODE", "api")
    result = run_default_ingestion(batch_size=batch_size, mode=mode)
    print(result)


if __name__ == "__main__":
    main()
