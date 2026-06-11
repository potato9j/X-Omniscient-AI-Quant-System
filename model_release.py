from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trend_predictor import DEFAULT_CONFIG_PATH, load_config, setup_logging, train_model


DEFAULT_RELEASE_DIR = Path("models/releases")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def package_model(config_path: Path, release_dir: Path) -> dict[str, Any]:
    config = load_config(config_path)
    setup_logging(config.log_path)
    training_result = train_model(config)
    if not training_result.get("trained"):
        return {
            "packaged": False,
            "reason": training_result.get("reason", "training did not produce a model"),
            "training_result": training_result,
        }

    model_path = config.model_path
    metadata_path = config.metadata_path
    metadata = load_json(metadata_path)
    model_version = str(metadata["model_version"])

    release_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = release_dir / f"{model_version}_manifest.json"
    zip_path = release_dir / f"{model_version}.zip"

    manifest = {
        "model_version": model_version,
        "created_at": utc_now_iso(),
        "model_type": metadata.get("model_type"),
        "feature_schema_version": 2,
        "feature_columns": metadata.get("feature_columns", []),
        "horizon_steps": metadata.get("horizon_steps"),
        "rows": metadata.get("rows"),
        "metrics": metadata.get("metrics", {}),
        "artifacts": {
            "model": {
                "path": "predictor_latest.joblib",
                "sha256": sha256_file(model_path),
                "bytes": model_path.stat().st_size,
            },
            "metadata": {
                "path": "metadata.json",
                "sha256": sha256_file(metadata_path),
                "bytes": metadata_path.stat().st_size,
            },
        },
        "distribution": {
            "target": "github_release_asset",
            "asset_name": zip_path.name,
        },
    }
    write_json(manifest_path, manifest)

    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(model_path, "predictor_latest.joblib")
        archive.write(metadata_path, "metadata.json")
        archive.write(manifest_path, "manifest.json")

    return {
        "packaged": True,
        "model_version": model_version,
        "zip_path": str(zip_path),
        "zip_sha256": sha256_file(zip_path),
        "manifest_path": str(manifest_path),
        "training_result": training_result,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train and package a release model for Omniscient AI Quant System"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--release-dir", type=Path, default=DEFAULT_RELEASE_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = package_model(args.config, args.release_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
