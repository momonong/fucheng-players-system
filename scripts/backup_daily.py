from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fucheng.cli import backup


def main() -> None:
    parser = argparse.ArgumentParser(description="建立帶有台北時間戳的一致性 SQLite 備份")
    parser.add_argument("directory")
    args = parser.parse_args()
    directory = Path(args.directory)
    stamp = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y%m%d-%H%M%S")
    backup(argparse.Namespace(output=str(directory / f"fucheng-{stamp}.db"), force=False))


if __name__ == "__main__":
    main()
