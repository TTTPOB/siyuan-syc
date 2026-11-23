"""Run SiYuan sync over HTTP and verify its reported outcome."""

import json
import re
from urllib.parse import quote

import click

from .config import Instance
from .transport import api_error, request

GET_INFO = "/api/sync/getSyncInfo"
PERFORM = "/api/sync/performSync"
GET_SECTION = "/api/setting/getSection"
LAN_TRAFFIC = '<br data-type="lanSyncTraffic">'


def _json_request(
    instance: Instance,
    method: str,
    endpoint: str,
    body: dict[str, str] | None = None,
    timeout: float = 60,
) -> object:
    response = request(instance, method, endpoint, json=body, timeout=timeout)
    try:
        return response.json()
    except (json.JSONDecodeError, UnicodeError):
        raise click.ClickException(
            f"SiYuan {endpoint}: invalid JSON response"
        ) from None


def _api_post(
    instance: Instance, endpoint: str, body: dict[str, str], timeout: float = 60
) -> object:
    result = _json_request(instance, "POST", endpoint, body, timeout)
    if (
        not isinstance(result, dict)
        or type(result.get("code")) is not int
        or result["code"] != 0
    ):
        raise api_error(endpoint, result if isinstance(result, dict) else {})
    return result.get("data")


def _state(instance: Instance) -> tuple[int, str]:
    data = _api_post(instance, GET_INFO, {})
    match data:
        case {"synced": int(synced), "stat": str(stat)}:
            return synced, stat
    raise click.ClickException(f"SiYuan {GET_INFO}: missing sync timestamp or status")


def _success_pattern(instance: Instance) -> re.Pattern[str]:
    data = _api_post(instance, GET_SECTION, {"namespace": "appearance"})
    match data:
        case {"conf": {"appearance": {"lang": str(lang)}}} if lang:
            pass
        case _:
            raise click.ClickException(
                f"SiYuan {GET_SECTION}: missing appearance language"
            )
    endpoint = f"/appearance/langs/{quote(lang, safe='')}.json"
    pack = _json_request(instance, "GET", endpoint)
    match pack:
        case {"_kernel": {"150": str(template)}} if template:
            pass
        case _:
            raise click.ClickException(
                f"SiYuan {endpoint}: missing sync success template"
            )
    # Language(150) uses %d for file/chunk counts and %s for human-readable sizes.
    return re.compile(
        re.escape(template).replace("%d", "[0-9]+").replace("%s", "[^<>]+")
    )


def sync_instance(instance: Instance) -> tuple[bool, str]:
    pattern = _success_pattern(instance)
    before = _state(instance)
    # performSync blocks until the sync finishes; a first sync can take minutes.
    _api_post(instance, PERFORM, {}, timeout=600)
    after = _state(instance)
    synced, stat = after
    if synced != before[0] and pattern.fullmatch(stat.partition(LAN_TRAFFIC)[0]):
        return True, stat
    message = f"Sync could not be confirmed. Current status: {stat or '(empty)'}"
    if before == after:
        message += (
            ". Sync did not appear to run; check whether sync is enabled, "
            "you are logged in to a SiYuan account, and the sync provider is configured."
        )
    return False, message
