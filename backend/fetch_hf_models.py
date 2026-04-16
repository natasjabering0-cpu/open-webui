#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys

from open_webui.apps.hf_model_catalog import HF_MODELS_DB_PATH, initialize_catalog_database, sync_hf_models


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Fetch llama-related Hugging Face models and upsert them into hf_models.db.'
    )
    parser.add_argument('--limit', type=int, default=200, help='Maximum number of HF models to fetch (default: 200)')
    parser.add_argument('--timeout', type=int, default=30, help='HTTP timeout in seconds (default: 30)')
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    args = parse_args()

    try:
        initialize_catalog_database()
        summary = sync_hf_models(limit=args.limit, timeout=args.timeout)
    except Exception as exc:
        logging.getLogger(__name__).exception('Failed to refresh Hugging Face model catalog: %s', exc)
        return 1

    print(
        json.dumps(
            {
                'database': str(HF_MODELS_DB_PATH),
                **summary,
            },
            indent=2,
        )
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
