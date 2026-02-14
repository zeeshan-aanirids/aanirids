from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import frappe
import requests
from frappe.utils import cint


DEFAULT_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class AaniridsRequestConfig:
	base_url: str
	timeout_seconds: int
	verify_ssl: bool
	auth_header: str | None
	default_isp_id: int | None
	default_branch_id: int | None
	default_user_id: int | None
	default_username: str | None
	debug_log_requests: bool


def _get_config() -> AaniridsRequestConfig:
	if not frappe.db.exists("DocType", "Aanirids ISP Settings"):
		frappe.throw("Missing DocType: Aanirids ISP Settings. Please run migrations.")

	settings = frappe.get_single("Aanirids ISP Settings")

	base_url = (settings.base_url or "").strip()
	if not base_url:
		frappe.throw("Set Aanirids ISP Settings → Base URL before using the integration.")

	trimmed = base_url.rstrip("/")
	if not trimmed.endswith("/api"):
		trimmed = f"{trimmed}/api"

	auth_header = None
	# If api_token is unset, Frappe will otherwise emit "Password not found..." messages.
	token = settings.get_password("api_token", raise_exception=False)

	if token:
		auth_header = f"Bearer {token}"

	return AaniridsRequestConfig(
		base_url=trimmed,
		timeout_seconds=int(settings.timeout_seconds or DEFAULT_TIMEOUT_SECONDS),
		verify_ssl=bool(cint(settings.verify_ssl)),
		auth_header=auth_header,
		default_isp_id=int(settings.default_isp_id) if settings.default_isp_id else None,
		default_branch_id=int(settings.default_branch_id) if settings.default_branch_id else None,
		default_user_id=int(settings.default_user_id) if settings.default_user_id else None,
		default_username=(settings.default_username or "").strip() or None,
		debug_log_requests=bool(cint(settings.debug_log_requests)),
	)


def _normalize_path(path: str) -> str:
	if not path:
		return ""
	path = f"/{path.lstrip('/')}"
	if path == "/api":
		return ""
	if path.startswith("/api/"):
		return path[len("/api") :]
	return path


def _redact(value: Any) -> Any:
	if isinstance(value, dict):
		redacted: dict[str, Any] = {}
		for k, v in value.items():
			lk = str(k).lower()
			if "password" in lk or "token" in lk:
				redacted[k] = "***"
			else:
				redacted[k] = _redact(v)
		return redacted
	if isinstance(value, list):
		return [_redact(v) for v in value]
	return value


def request(
	method: str,
	path: str,
	*,
	params: dict[str, Any] | None = None,
	json: Any | None = None,
	data: Any | None = None,
	files: Any | None = None,
	headers: dict[str, str] | None = None,
	timeout_seconds: int | None = None,
	verify_ssl: bool | None = None,
	scope: bool = False,
	expected_statuses: tuple[int, ...] = (200,),
) -> requests.Response:
	cfg = _get_config()

	normalized_path = _normalize_path(path)
	url = f"{cfg.base_url}{normalized_path}"

	final_headers: dict[str, str] = {"Accept": "application/json"}
	if cfg.auth_header:
		final_headers["Authorization"] = cfg.auth_header

	final_params = dict(params or {})

	if scope:
		if cfg.default_isp_id is not None and "isp_id" not in final_params:
			final_params["isp_id"] = cfg.default_isp_id
		if cfg.default_branch_id is not None and "branch_id" not in final_params:
			final_params["branch_id"] = cfg.default_branch_id
		if cfg.default_isp_id is not None:
			final_headers.setdefault("x-isp-id", str(cfg.default_isp_id))
		if cfg.default_branch_id is not None:
			final_headers.setdefault("x-branch-id", str(cfg.default_branch_id))
		if cfg.default_user_id is not None:
			final_headers.setdefault("x-user-id", str(cfg.default_user_id))
		if cfg.default_username is not None:
			final_headers.setdefault("x-username", cfg.default_username)

	if headers:
		final_headers.update(headers)

	timeout = timeout_seconds if timeout_seconds is not None else cfg.timeout_seconds
	verify = verify_ssl if verify_ssl is not None else cfg.verify_ssl

	if cfg.debug_log_requests:
		frappe.logger("aanirids_isp.api").info(
			"Aanirids API request",
			extra={
				"method": method,
				"url": url,
				"params": _redact(final_params),
				"json": _redact(json),
			},
		)

	try:
		resp = requests.request(
			method=method,
			url=url,
			params=final_params or None,
			json=json,
			data=data,
			files=files,
			headers=final_headers,
			timeout=timeout,
			verify=verify,
		)
	except requests.RequestException as exc:
		frappe.throw(f"Failed to connect to Aanirids API: {exc}")

	if resp.status_code not in expected_statuses:
		msg = resp.text
		try:
			msg = resp.json()
		except Exception:
			pass
		frappe.throw(
			f"Aanirids API error {resp.status_code} for {method} {normalized_path}: {msg}"
		)

	return resp


def get_json(path: str, *, params: dict[str, Any] | None = None, scope: bool = False) -> Any:
	return request("GET", path, params=params, scope=scope, expected_statuses=(200,)).json()


def post_json(
	path: str,
	*,
	json: Any | None = None,
	params: dict[str, Any] | None = None,
	scope: bool = False,
	expected_statuses: tuple[int, ...] = (200, 201),
) -> Any:
	return request(
		"POST",
		path,
		json=json,
		params=params,
		scope=scope,
		expected_statuses=expected_statuses,
	).json()


def put_json(
	path: str,
	*,
	json: Any | None = None,
	params: dict[str, Any] | None = None,
	scope: bool = False,
	expected_statuses: tuple[int, ...] = (200, 201),
) -> Any:
	return request(
		"PUT",
		path,
		json=json,
		params=params,
		scope=scope,
		expected_statuses=expected_statuses,
	).json()


def delete(
	path: str,
	*,
	params: dict[str, Any] | None = None,
	scope: bool = False,
	expected_statuses: tuple[int, ...] = (200, 204),
) -> None:
	request("DELETE", path, params=params, scope=scope, expected_statuses=expected_statuses)
