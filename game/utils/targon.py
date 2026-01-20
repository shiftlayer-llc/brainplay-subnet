import asyncio
from game.utils.epistula import generate_header


async def get_metadata(self, endpoint: str) -> dict:
    """Retrieves the metadata of a Targon endpoint.

    Args:
        endpoint (str): The Targon endpoint URL.

    Returns:
        dict: The metadata dictionary if successful, empty dict otherwise.
    """
    try:
        url = f"https://{endpoint}.serverless.targon.com/metadata"
        headers = generate_header(
            self.wallet.hotkey, b"", self.metagraph.hotkeys.get(self.uid, "")
        )
        response = await self.http_client.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return {}
    except Exception as e:
        return {}


async def _check_image_hash(self, endpoint: str) -> bool:
    """Checks the image hash of a Targon endpoint.

    Args:
        endpoint (str): The Targon endpoint URL to check.

    Returns:
        bool: True if the image hash matches, False otherwise.
    """
    try:
        data = await self.get_metadata(endpoint)
        if "image_hash" in data:
            return data.get("image_hash") == self.EXPECTED_IMAGE_HASH
        return False
    except Exception as e:
        return False


async def _check_metadata(self, endpoint: str, hotkey: str) -> bool:
    """Checks the metadata of a Targon endpoint.

    Args:
        endpoint (str): The Targon endpoint URL to check.

    Returns:
        bool: True if the metadata matches, False otherwise.
    """
    try:
        url = f"https://{endpoint}.serverless.targon.com/metadata"
        headers = generate_header(self.wallet.hotkey, b"", hotkey)
        response = await self.http_client.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data["sglang_port_open"]:
                return True
        return False
    except Exception as e:
        return False


async def _check_endpoint(self, uid: int, endpoint: str) -> bool:
    try:
        if not await _check_image_hash(self, endpoint):
            return False
        if not await _check_metadata(self, endpoint, self.metagraph.hotkeys[uid]):
            return False
        return True
    except Exception as e:
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
            if result:
                responsive_uids.append(uid)
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            continue

    return responsive_uids
