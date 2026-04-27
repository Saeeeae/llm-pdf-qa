from __future__ import annotations

import ipaddress
import os
import socket
from typing import Optional
from urllib.parse import urlparse

BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}
BLOCKED_NETS = [ipaddress.ip_network(n) for n in [
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "169.254.0.0/16", "0.0.0.0/8", "::1/128", "fc00::/7", "fe80::/10",
]]


def _is_blocked_host(host: str) -> bool:
    if host in BLOCKED_HOSTS:
        return True
    try:
        for _fam, _, _, _, sa in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(sa[0])
            if any(ip in n for n in BLOCKED_NETS):
                return True
    except socket.gaierror:
        return True  # 해석 실패 시 차단
    return False


def _csv_env(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [v.strip().lower() for v in raw.split(",") if v.strip()]


def normalize_domain(domain: str) -> str:
    d = domain.strip().lower()
    if "://" in d:
        d = urlparse(d).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def domain_matches(host: str, domain: str) -> bool:
    host = normalize_domain(host)
    domain = normalize_domain(domain)
    return host == domain or host.endswith("." + domain)


def is_url_allowed(url: str, request_domains: Optional[list[str]] = None) -> tuple[bool, Optional[str]]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, "invalid_url"

    raw_host = parsed.hostname or ""
    if _is_blocked_host(raw_host):
        return False, "ssrf_blocked"

    host = normalize_domain(parsed.netloc)
    denied = _csv_env("M8_DENIED_DOMAINS")
    if any(domain_matches(host, d) for d in denied):
        return False, "domain_denied"

    requested = [normalize_domain(d) for d in (request_domains or []) if d.strip()]
    configured_allow = _csv_env("M8_ALLOWED_DOMAINS")
    active_allow = requested or configured_allow
    if active_allow and not any(domain_matches(host, d) for d in active_allow):
        return False, "domain_not_allowed"

    return True, None
