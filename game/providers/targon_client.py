import os
import bittensor as bt
import asyncio
import aiohttp
from game.common.epistula import generate_header
from game.common.targon import extract_workload_uid, normalize_endpoint_url
from game import __image_hash__


def _log_yellow_info(message: str) -> None:
    bt.logging.info(f"\033[33m{message}\033[0m")


async def get_metadata(self, endpoint: str, hotkey: str) -> dict:
    """Retrieves the metadata of a Targon endpoint.

    Args:
        endpoint (str): The Targon endpoint URL.
        hotkey (str): The hotkey associated with the endpoint.
    Returns:
        dict: The metadata dictionary if successful, empty dict otherwise.
    """
    try:
        url = f"{normalize_endpoint_url(endpoint)}/meta"
        headers = generate_header(self.wallet.hotkey, b"", hotkey)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
        return {}
    except Exception as e:
        bt.logging.error(f"Error retrieving metadata for endpoint {endpoint}: {e}")
        return {}


async def _check_image_hash(self, endpoint: str, uid: int | None = None) -> bool:
    """Checks the image hash of a Targon endpoint.

    Args:
        endpoint (str): The Targon endpoint URL to check.

    Returns:
        bool: True if the image hash matches, False otherwise.
    """
    try:
        url = f"https://api.targon.com/tha/v2/workloads/verify"
        workload_uid = extract_workload_uid(endpoint)
        headers = {
            "Authorization": f"Bearer {os.getenv('TARGON_API_KEY')}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            payloads = [{"uid": workload_uid, "digest": __image_hash__}]
            normalized_url = normalize_endpoint_url(endpoint)
            if workload_uid.startswith("serv-"):
                payloads.append({"url": normalized_url})

            response = None
            data = None
            for payload in payloads:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                ) as current_response:
                    response = current_response
                    if current_response.status != 200:
                        continue
                    try:
                        data = await current_response.json()
                    except aiohttp.ContentTypeError:
                        body = await current_response.text()
                        uid_text = "?" if uid is None else str(uid)
                        _log_yellow_info(f"{uid_text} {endpoint}: invalid_json {body}")
                        return False
                    break

            if response is None or response.status != 200:
                body = await response.text() if response is not None else "no_response"
                uid_text = "?" if uid is None else str(uid)
                _log_yellow_info(
                    f"{uid_text} {endpoint}: {response.status if response else 'n/a'} {body}"
                )
                return False

            if "verified" in (data or {}):
                if bool(data.get("verified")):
                    return True
            elif "image_hash" in (data or {}):
                if data.get("image_hash") == __image_hash__:
                    return True

            bt.logging.info(
                f"Image digest verification failed for endpoint {endpoint}: "
                f"workload_uid={workload_uid}"
            )
        return False
    except Exception as e:
        uid_text = "?" if uid is None else str(uid)
        _log_yellow_info(f"{uid_text} {endpoint}: exception {e}")
        return False


async def _check_metadata(self, endpoint: str, hotkey: str) -> bool:
    """Checks the metadata of a Targon endpoint.

    Args:
        endpoint (str): The Targon endpoint URL to check.

    Returns:
        bool: True if the metadata matches, False otherwise.
    """
    try:
        bt.logging.debug(f"Checking metadata for endpoint {endpoint}")
        meta = await get_metadata(self, endpoint, hotkey)
        if isinstance(meta, dict) and meta.get("sglang_port_open"):
            return True
        return False
    except TypeError as e:
        # Hide noisy malformed metadata shape errors during endpoint probing.
        bt.logging.debug(f"Malformed metadata for endpoint {endpoint}: {e}")
        return False
    except Exception as e:
        bt.logging.error(f"Error checking metadata for endpoint {endpoint}: {e}")
        return False


async def _check_endpoint(self, uid: int, endpoint: str) -> bool:
    try:
        bt.logging.debug(f"Checking endpoint {endpoint} for UID {uid}")
        if not await _check_image_hash(self, endpoint, uid=uid):
            return False
        bt.logging.debug(f"Image hash check passed for endpoint {endpoint}")
        if not await _check_metadata(self, endpoint, self.metagraph.hotkeys[uid]):
            return False
        return True
    except Exception as e:
        bt.logging.error(f"Error checking endpoint {endpoint}: {e}")
        return False


async def check_endpoints(
    self, targon_endpoints: dict[int, str], timeout: int = 30
) -> list[int]:
    """Checks the given Targon endpoints for responsiveness.

    Args:
        targon_endpoints (dict[int, str]): A dictionary mapping UIDs to their Targon endpoints.
        timeout (int): Timeout in seconds for each endpoint check.

    Returns:
        Tuple[List[int], List[int]]: A tuple containing a list of responsive UIDs and a list of unresponsive UIDs.
    """
    responsive_uids = []

    # make tasks for each endpoint check
    tasks = []
    for uid, endpoint in targon_endpoints.items():
        tasks.append(
            (
                uid,
                asyncio.wait_for(_check_endpoint(self, uid, endpoint), timeout=timeout),
            )
        )
    # gather results
    for uid, task in tasks:
        try:
            result = await task
            bt.logging.debug(f"Endpoint {targon_endpoints[uid]} responsive: {result}")
            if result:
                responsive_uids.append(uid)
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            bt.logging.error(f"Error checking endpoint {endpoint}: {e}")
            continue

    return responsive_uids
