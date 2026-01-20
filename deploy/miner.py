#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path

import bittensor as bt
from targon.cli.auth import get_stored_key
from targon.client.client import Client
from targon.utils.config_parser import load_config, config_to_serverless_requests

NETUID_DEFAULT = 117
DEPLOY_DIR = Path(__file__).resolve().parent


def _ensure_typing_self() -> None:
    """Backfill typing.Self for Python < 3.11 so the Targon SDK can import."""
    import typing

    if hasattr(typing, "Self"):
        return
    try:
        from typing_extensions import Self as _Self
    except ImportError as exc:
        raise RuntimeError(
            "Targon SDK requires typing.Self. Install typing_extensions or use Python 3.11+."
        ) from exc
    typing.Self = _Self


def _resolve_competition(value: str) -> tuple[str, Path, str]:
    normalized = value.strip().lower()
    if normalized in {"clue", "codenames_clue"}:
        return "codenames_clue", DEPLOY_DIR / "clue.json", "clue"
    if normalized in {"guess", "codenames_guess"}:
        return "codenames_guess", DEPLOY_DIR / "guess.json", "guess"
    raise ValueError("competition must be one of: clue, guess")


def _get_api_key() -> str:
    env_key = os.getenv("TARGON_API_KEY")
    if env_key:
        return env_key
    stored_key = get_stored_key()
    if stored_key:
        return stored_key
    raise RuntimeError("TARGON_API_KEY not set and no stored credentials found.")


def _deploy_targon(config_path: Path) -> dict[str, str]:
    _ensure_typing_self()

    config = load_config(config_path)
    requests = config_to_serverless_requests(config)
    if not requests:
        raise RuntimeError(f"No containers defined in {config_path}")

    api_key = _get_api_key()
    client = Client(api_key=api_key)

    async def _deploy():
        responses: dict[str, str] = {}
        for request in requests:
            resource = await client.async_serverless.deploy_container(request)
            responses[request.name] = resource.uid
        return responses

    return client.run_async(_deploy)


def _load_existing_commitment(
    subtensor: bt.Subtensor,
    netuid: int,
    hotkey_ss58: str,
) -> dict:
    uid = subtensor.get_uid_for_hotkey_on_subnet(hotkey_ss58, netuid)
    if uid is None:
        return {}
    existing_raw = subtensor.get_commitment(netuid, uid)
    if not existing_raw:
        return {}
    try:
        return json.loads(existing_raw)
    except json.JSONDecodeError:
        return {}


def _commit_endpoint(
    wallet: bt.Wallet,
    network: str,
    netuid: int,
    competition_key: str,
    endpoint_uid: str,
    period: int | None,
) -> None:
    subtensor = bt.Subtensor(network)
    existing = _load_existing_commitment(subtensor, netuid, wallet.hotkey.ss58_address)
    print(f"Existing commitment data: {existing}")
    existing[competition_key] = endpoint_uid
    data_to_str = json.dumps(existing)
    ok = subtensor.set_commitment(wallet, netuid, data_to_str, period=period)
    print(f"✅ Committed endpoint {endpoint_uid} for competition {competition_key}")
    if not ok:
        raise RuntimeError("Failed to set commitment on chain.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deploy a Targon serverless miner and commit the endpoint to chain."
    )
    parser.add_argument(
        "--competition",
        required=True,
        help="Competition type: clue or guess.",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Model name or path for SGLang.",
    )
    parser.add_argument(
        "--sglang-extra-args",
        default="",
        help="Extra args passed to the SGLang server.",
    )
    parser.add_argument(
        "--wallet",
        required=True,
        help="Bittensor wallet name.",
    )
    parser.add_argument(
        "--hotkey",
        default="default",
        help="Bittensor hotkey name.",
    )
    parser.add_argument(
        "--wallet-path",
        default=None,
        help="Optional path to the bittensor wallet directory.",
    )
    parser.add_argument(
        "--netuid",
        type=int,
        default=NETUID_DEFAULT,
        help=f"Subnet netuid (default: {NETUID_DEFAULT}).",
    )
    parser.add_argument(
        "--network",
        default="finney",
        help=f"Subnet netuid (default: {NETUID_DEFAULT}).",
    )
    parser.add_argument(
        "--commit-period",
        type=int,
        default=None,
        help="Optional commitment period override.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        competition_key, config_path, container_name = _resolve_competition(
            args.competition
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 2

    wallet = bt.Wallet(name=args.wallet, hotkey=args.hotkey, path=args.wallet_path)
    hotkey_ss58 = wallet.hotkey.ss58_address

    os.environ["MODEL"] = args.model
    os.environ["SGLANG_EXTRA_ARGS"] = args.sglang_extra_args
    os.environ["MINER_HOTKEY"] = hotkey_ss58

    try:
        deployed = _deploy_targon(config_path)
        print(f"✅ Successfully deployed a targon serverless container: {deployed}")
    except Exception as exc:
        print(f"Failed to deploy via Targon: {exc}", file=sys.stderr)
        return 1

    endpoint_uid = deployed.get(container_name)
    if endpoint_uid is None:
        if len(deployed) == 1:
            endpoint_uid = next(iter(deployed.values()))
        else:
            print(
                f"Expected container '{container_name}' but got {sorted(deployed)}",
                file=sys.stderr,
            )
            return 1

    try:
        _commit_endpoint(
            wallet=wallet,
            network=args.network,
            netuid=args.netuid,
            competition_key=competition_key,
            endpoint_uid=endpoint_uid,
            period=args.commit_period,
        )
    except Exception as exc:
        print(f"Failed to commit endpoint: {exc}", file=sys.stderr)
        return 1

    print(f"✅ Successfully committed endpoint {endpoint_uid} to chain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
