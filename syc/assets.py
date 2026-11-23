"""Transfer local files with SiYuan's raw asset APIs."""

import json
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import click
import httpx

from .config import Instance
from .transport import proxy_for

UPLOAD = "/api/asset/upload"
GET_FILE = "/api/file/getFile"


def _post(instance: Instance, endpoint: str, **kwargs: Any) -> httpx.Response:
    # Let HTTPX set the JSON or multipart Content-Type for this particular request.
    headers = {
        k: v for k, v in instance.headers().items() if k.lower() != "content-type"
    }
    try:
        with httpx.Client(
            headers=headers, timeout=60, trust_env=False, proxy=proxy_for(instance.url)
        ) as client:
            response = client.post(instance.url + endpoint, **kwargs)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise click.ClickException(
            f"SiYuan {endpoint}: HTTP {exc.response.status_code}"
        ) from None
    except (httpx.RequestError, httpx.InvalidURL, UnicodeError) as exc:
        raise click.ClickException(f"SiYuan {endpoint}: {type(exc).__name__}") from None
    return response


def _api_error(endpoint: str, result: dict[str, Any]) -> click.ClickException:
    msg = result.get("msg")
    detail = f" ({msg})" if isinstance(msg, str) and msg else ""
    return click.ClickException(
        f"SiYuan {endpoint}: API code {result.get('code', 'missing')}{detail}"
    )


def upload_assets(instance: Instance, files: tuple[Path, ...]) -> list[dict[str, str]]:
    names = [path.name for path in files]
    if len(set(names)) != len(names):
        raise click.ClickException("Upload filenames must be distinct")
    with ExitStack() as stack:
        parts = [
            ("file[]", (path.name, stack.enter_context(path.open("rb"))))
            for path in files
        ]
        response = _post(
            instance, UPLOAD, data={"assetsDirPath": "/assets/"}, files=parts
        )
    try:
        result = response.json()
    except (json.JSONDecodeError, UnicodeError):
        raise click.ClickException(
            f"SiYuan {UPLOAD}: invalid JSON response; assets may already exist"
        ) from None
    if (
        not isinstance(result, dict)
        or type(result.get("code")) not in (int, float)
        or result["code"] != 0
    ):
        raise _api_error(UPLOAD, result if isinstance(result, dict) else {})
    data = result.get("data")
    if isinstance(data, dict) and data.get("errFiles"):
        raise click.ClickException(
            "SiYuan reported failed files; some assets may already exist. Inspect before retrying."
        )
    mapping = data.get("succMap") if isinstance(data, dict) else None
    if not isinstance(mapping, dict) or not all(
        isinstance(mapping.get(name), str) and mapping[name].startswith("assets/")
        for name in names
    ):
        raise click.ClickException(
            "SiYuan returned an incomplete asset mapping; assets may already exist. Inspect before retrying."
        )
    return [{"file": str(path), "assetPath": mapping[path.name]} for path in files]


def get_asset(instance: Instance, asset: str, output: Path | None) -> dict[str, Any]:
    if (
        not asset.startswith("assets/")
        or "\\" in asset
        or any(part in {"", ".", ".."} for part in asset.split("/"))
    ):
        raise click.ClickException(
            "Use a relative SiYuan asset path such as assets/example.png"
        )
    response = _post(instance, GET_FILE, json={"path": "/data/" + asset})
    media_type = response.headers.get("Content-Type", "application/octet-stream")
    if "application/json" in media_type.lower():
        try:
            result = response.json()
        except (json.JSONDecodeError, UnicodeError):
            result = None  # A downloaded asset can itself be malformed JSON.
        if (
            isinstance(result, dict)
            and type(code := result.get("code")) in (int, float)
            and code != 0
        ):
            raise _api_error(GET_FILE, result)

    if output is None:
        output = Path(tempfile.mkdtemp(prefix="syc-asset-")) / Path(asset).name
    try:
        with output.open("xb") as handle:
            handle.write(response.content)
    except FileExistsError:
        raise click.ClickException(f"Output already exists: {output}") from None
    return {
        "asset": asset,
        "path": str(output.absolute()),
        "bytes": len(response.content),
        "mediaType": media_type,
    }
