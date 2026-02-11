#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from dotenv import load_dotenv

import bittensor as bt
import httpx
from targon.cli.auth import get_stored_key
from targon.client.client import Client
from targon.utils.config_parser import load_config, config_to_serverless_requests

bt.logging.off()

load_dotenv()

NETUID_DEFAULT = 117
DEPLOY_DIR = Path(__file__).resolve().parent
META_REQUEST_TIMEOUT_SEC = 30
META_POLL_INTERVAL_SEC = 3


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


def _resolve_competition(value: str) -> tuple[list[str], Path, str]:
    normalized = value.strip().lower()
    config_path = DEPLOY_DIR / "codenames.json"
    if normalized in {"codenames"}:
        return ["codenames"], config_path, "brainplay-codenames"
    if normalized in {"all"}:
        return ["codenames"], config_path, "brainplay-all"
    raise ValueError("competition must be one of: codenames, all")


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


def _build_endpoint_url(endpoint_uid: str) -> str:
    endpoint = endpoint_uid.strip().rstrip("/")
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    if "serverless.targon.com" in endpoint:
        return f"https://{endpoint}"
    return f"https://{endpoint}.serverless.targon.com"


def _normalize_endpoint_uid(endpoint_uid: str) -> str:
    endpoint = endpoint_uid.strip().rstrip("/")
    if endpoint.startswith(("http://", "https://")):
        host = urlparse(endpoint).netloc
        if host:
            endpoint = host
    if endpoint.endswith(".serverless.targon.com"):
        endpoint = endpoint.split(".serverless.targon.com", 1)[0]
    return endpoint


def _build_epistula_headers(hotkey: bt.Keypair, signed_for: str) -> dict[str, str]:
    timestamp = round(time.time() * 1000)
    nonce = str(uuid4())
    req_hash = sha256(b"").hexdigest()
    signature = hotkey.sign(f"{req_hash}.{nonce}.{timestamp}.{signed_for}").hex()
    return {
        "Epistula-Version": "2",
        "Epistula-Timestamp": str(timestamp),
        "Epistula-Uuid": nonce,
        "Epistula-Signed-By": hotkey.ss58_address,
        "Epistula-Signed-For": signed_for,
        "Epistula-Request-Signature": "0x" + signature,
    }


def _render_config_with_name(
    config_path: Path, container_name: str, output_path: Path
) -> Path:
    contents = config_path.read_text(encoding="utf-8")
    rendered = contents.replace("${NAME}", container_name)
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


def _delete_targon_container(endpoint_uid: str) -> None:
    _ensure_typing_self()
    api_key = _get_api_key()
    client = Client(api_key=api_key)
    resource_id = _normalize_endpoint_uid(endpoint_uid)

    async def _delete():
        return await client.async_serverless.delete_container(resource_id)

    client.run_async(_delete)


def _wait_for_endpoint_ready(endpoint_uid: str, hotkey: bt.Keypair) -> bool:
    base_url = _build_endpoint_url(endpoint_uid)
    meta_url = f"{base_url}/meta"

    with httpx.Client(timeout=META_REQUEST_TIMEOUT_SEC) as client:
        frame_idx = 0
        last_len = 0
        while True:
            status_message = f"⏳ Waiting for endpoint readiness: {base_url}"
            headers = _build_epistula_headers(hotkey, hotkey.ss58_address)
            try:
                response = client.get(meta_url, headers=headers)
            except httpx.HTTPError as exc:
                dots = "." * ((frame_idx % 3) + 1)
                message = f"{status_message} {dots}"
                last_len = _print_status_line(message, last_len)
                frame_idx += 1
                time.sleep(META_POLL_INTERVAL_SEC)
                continue

            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError:
                    status_message = (
                        "⏳ waiting for endpoint readiness: invalid JSON response"
                    )
                else:
                    sglang_process = payload.get("sglang_process") or {}
                    returncode = sglang_process.get("returncode")
                    running = sglang_process.get("running")
                    if isinstance(returncode, int) and returncode < 0:
                        print()
                        print(
                            "SGLang process crashed with returncode "
                            f"{returncode}. Deleting deployed app..."
                        )
                        try:
                            _delete_targon_container(endpoint_uid)
                        except Exception as exc:
                            print(
                                f"Failed to delete deployed app {endpoint_uid}: {exc}",
                                file=sys.stderr,
                            )
                        return False

                    if running is True:
                        status_message = "⏳ sglang is loading model"
                    elif running is False:
                        status_message = "⚠️ sglang process not running"
                    else:
                        status_message = "⏳ waiting for sglang process"
                    if payload.get("sglang_port_open") is True:
                        message = f"✅ Endpoint ready: {base_url}"
                        _print_status_line(message, last_len)
                        print()
                        return True
            else:
                body = response.text.strip()

            dots = "." * ((frame_idx % 3) + 1)
            message = f"{status_message} {dots}"
            last_len = _print_status_line(message, last_len)
            frame_idx += 1
            time.sleep(META_POLL_INTERVAL_SEC)
    return False


def _print_status_line(message: str, last_len: int) -> int:
    padded = message.ljust(last_len)
    print("\r" + padded, end="", flush=True)
    return len(message)


def _load_existing_commitment(
    subtensor: bt.Subtensor,
    netuid: int,
    hotkey_ss58: str,
) -> dict:
    uid = subtensor.get_uid_for_hotkey_on_subnet(hotkey_ss58, netuid)
    if uid is None:
        return {}
    try:
        existing_raw = subtensor.get_commitment(netuid, uid)
        if not existing_raw:
            return {}
    except Exception:
        return {}
    try:
        return json.loads(existing_raw)
    except json.JSONDecodeError:
        return {}


def _commit_endpoint(
    wallet: bt.Wallet,
    network: str,
    netuid: int,
    competition_keys: list[str],
    endpoint_uid: str,
    period: int | None,
) -> None:
    subtensor = bt.Subtensor(network)
    existing = _load_existing_commitment(subtensor, netuid, wallet.hotkey.ss58_address)
    print(f"ℹ️ Existing commitment data: {existing}")
    # Filter out deprecated competitions
    existing = {}
    for competition_key in competition_keys:
        existing[competition_key] = endpoint_uid
    data_to_str = json.dumps(existing)
    ok = subtensor.set_commitment(wallet, netuid, data_to_str, period=period)
    competitions_label = ", ".join(competition_keys)
    print(f"✅ Committed endpoint {endpoint_uid} for competitions {competitions_label}")
    if not ok:
        raise RuntimeError("Failed to set commitment on chain.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deploy a Targon serverless miner and commit the endpoint to chain."
    )
    parser.add_argument(
        "--competition",
        required=True,
        help="Competition type: codenames or all.",
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
        "--reasoning",
        default="none",
        type=str.lower,
        choices=["none", "minimal", "low", "medium", "high", "xhigh"],
        help="Reasoning effort for the miner (default: none).",
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
        competition_keys, config_path, container_name = _resolve_competition(
            args.competition
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 2

    try:
        config_path = _render_config_with_name(
            config_path,
            container_name,
            Path("/tmp/codenames.json"),
        )
    except Exception as exc:
        print(f"Failed to render config with container name: {exc}", file=sys.stderr)
        return 1

    wallet = bt.Wallet(name=args.wallet, hotkey=args.hotkey, path=args.wallet_path)
    hotkey_ss58 = wallet.hotkey.ss58_address

    os.environ["MODEL"] = args.model
    os.environ["SGLANG_EXTRA_ARGS"] = args.sglang_extra_args
    os.environ["MINER_HOTKEY"] = hotkey_ss58
    os.environ["REASONING"] = args.reasoning
    os.environ["NAME"] = container_name

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
        if not _wait_for_endpoint_ready(endpoint_uid, wallet.hotkey):
            return 1
    except Exception as exc:
        print(f"Failed to confirm endpoint readiness: {exc}", file=sys.stderr)
        return 1

    try:
        _commit_endpoint(
            wallet=wallet,
            network=args.network,
            netuid=args.netuid,
            competition_keys=competition_keys,
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
