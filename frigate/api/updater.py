"""Authenticated bridge to the optional host update service."""

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from frigate.api.auth import require_role

router = APIRouter()
SOCKET = "/run/frigate-updater/updater.sock"


async def _request(method: str, path: str) -> dict:
    if not os.path.exists(SOCKET):
        raise HTTPException(503, "Host updater is not installed")
    try:
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=SOCKET), timeout=30
        ) as client:
            response = await client.request(method, f"http://host{path}")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Host updater is unavailable") from exc


def _logged_in_admin(request: Request) -> None:
    # Frigate's internal port grants admin to anonymous requests. Reject those
    # for the host update operation even if the role dependency accepts them.
    if request.headers.get("remote-user") in (None, "anonymous"):
        raise HTTPException(403, "Named admin login required")


@router.get("/updater/status", dependencies=[Depends(require_role(["admin"]))])
async def status(request: Request) -> dict:
    """Return host update status."""
    _logged_in_admin(request)
    return await _request("GET", "/status")


@router.post("/updater/start", dependencies=[Depends(require_role(["admin"]))])
async def start(request: Request) -> dict:
    """Queue an update on the host."""
    _logged_in_admin(request)
    return await _request("POST", "/start")
