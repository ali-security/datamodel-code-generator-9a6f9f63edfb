"""Tests for HTTP utilities."""

from __future__ import annotations

import socket
from ipaddress import ip_address
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from datamodel_code_generator import SchemaFetchError
from datamodel_code_generator.http import (
    MAX_HTTP_REDIRECTS,
    _embedded_ipv4,
    _get_redirect_headers,
    _get_url_origin,
    _is_safe_ip,
    get_body,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_get_body_raises_on_http_error(mocker: MockerFixture) -> None:
    """Test that get_body raises on HTTP error status codes."""
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.headers = {"content-type": "text/html"}
    mocker.patch("httpx.get", return_value=mock_response)

    with pytest.raises(SchemaFetchError, match="HTTP 404 error fetching"):
        get_body("https://example.com/missing.json")


def test_get_body_raises_on_html_response(mocker: MockerFixture) -> None:
    """Test that get_body raises when response is HTML instead of JSON/YAML."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html; charset=utf-8"}
    mocker.patch("httpx.get", return_value=mock_response)

    with pytest.raises(SchemaFetchError, match="Unexpected HTML response"):
        get_body("https://example.com/schema.json")


def test_get_body_succeeds_with_json_response(mocker: MockerFixture) -> None:
    """Test that get_body returns text for valid JSON responses."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.text = '{"type": "object"}'
    mocker.patch("httpx.get", return_value=mock_response)

    result = get_body("https://example.com/schema.json")
    assert result == '{"type": "object"}'


def test_get_body_succeeds_without_content_type(mocker: MockerFixture) -> None:
    """Test that get_body returns text when no Content-Type header is present."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_response.text = '{"type": "object"}'
    mocker.patch("httpx.get", return_value=mock_response)

    result = get_body("https://example.com/schema.json")
    assert result == '{"type": "object"}'


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/schema.json",
        "http://127.1/schema.json",
        "http://2130706433/schema.json",
        "http://0x7f000001/schema.json",
        "http://0177.0.0.1/schema.json",
        "http://[::1]/schema.json",
        "http://[::7f00:1]/schema.json",
        "http://[::ffff:0:7f00:1]/schema.json",
        "http://[64:ff9b::7f00:1]/schema.json",
        "http://[64:ff9b::a9fe:a9fe]/schema.json",
        "http://169.254.169.254/latest/meta-data",
        "http://localhost/schema.json",
        "http://schema.localhost/schema.json",
    ],
)
def test_get_body_blocks_unsafe_url_hosts(mocker: MockerFixture, url: str) -> None:
    """Block local and private network targets before fetching."""
    mock_get = mocker.patch("httpx.get")

    with pytest.raises(SchemaFetchError, match="--allow-private-network"):
        get_body(url)
    assert mock_get.call_count == 0


@pytest.mark.parametrize(
    ("addr", "expected"),
    [
        ("8.8.8.8", None),
        ("2606:4700::1", None),
        ("::ffff:127.0.0.1", "127.0.0.1"),
        ("::7f00:1", "127.0.0.1"),
        ("::ffff:0:7f00:1", "127.0.0.1"),
        ("64:ff9b::a9fe:a9fe", "169.254.169.254"),
    ],
)
def test_embedded_ipv4(addr: str, expected: str | None) -> None:
    """Return embedded IPv4 addresses from IPv6 wrapper forms."""
    result = _embedded_ipv4(ip_address(addr))
    assert (str(result) if result is not None else None) == expected


@pytest.mark.parametrize(
    ("addr", "safe"),
    [
        ("8.8.8.8", True),
        ("10.0.0.1", False),
        ("::ffff:8.8.8.8", True),
        ("64:ff9b::a9fe:a9fe", False),
        ("64:ff9b::808:808", True),
        ("::1", False),
    ],
)
def test_is_safe_ip(addr: str, safe: bool) -> None:
    """Validate embedded IPv4 addresses before trusting an IPv6 address."""
    assert _is_safe_ip(ip_address(addr)) is safe


@pytest.mark.parametrize(
    "resolved_ip",
    ["::ffff:127.0.0.1", "::ffff:0:a9fe:a9fe", "64:ff9b::a00:1"],
)
def test_get_body_blocks_hostname_resolving_to_ipv6_embedded_unsafe_ipv4(
    mocker: MockerFixture, resolved_ip: str
) -> None:
    """Block hostnames whose IPv6 DNS answers embed a local or private IPv4 target."""
    mocker.patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET6, socket.SOCK_STREAM, 0, "", (resolved_ip, 0, 0, 0))],
    )
    mock_get = mocker.patch("httpx.get")

    with pytest.raises(SchemaFetchError, match="--allow-private-network"):
        get_body("https://metadata.example.com/schema.json")
    assert mock_get.call_count == 0


@pytest.mark.parametrize(
    "url",
    [
        "http://127.1/schema.json",
        "http://2130706433/schema.json",
        "http://0x7f000001/schema.json",
        "http://0177.0.0.1/schema.json",
    ],
)
def test_get_body_blocks_unsafe_ipv4_literals_without_dns(mocker: MockerFixture, url: str) -> None:
    """Block legacy IPv4 literals without depending on platform DNS behavior."""
    mocker.patch("socket.getaddrinfo", side_effect=OSError)
    mock_get = mocker.patch("httpx.get")

    with pytest.raises(SchemaFetchError, match="--allow-private-network"):
        get_body(url)
    assert mock_get.call_count == 0


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.1/schema.json",
        "http://1.2.3.4.5/schema.json",
        "http://256.0.0.1/schema.json",
    ],
)
def test_get_body_handles_legacy_ipv4_literal_boundaries(mocker: MockerFixture, url: str) -> None:
    """Cover legacy IPv4 parser boundary cases without platform DNS behavior."""
    mocker.patch("socket.getaddrinfo", side_effect=OSError)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.text = '{"type": "object"}'
    mock_get = mocker.patch("httpx.get", return_value=mock_response)

    if url == "http://127.0.1/schema.json":
        with pytest.raises(SchemaFetchError, match="--allow-private-network"):
            get_body(url)
        assert mock_get.call_count == 0
    else:
        result = get_body(url)
        assert result == '{"type": "object"}'
        assert mock_get.call_count == 1


def test_get_body_allows_unsafe_url_host_with_explicit_opt_in(mocker: MockerFixture) -> None:
    """Allow trusted private network targets only when explicitly requested."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.text = '{"type": "object"}'
    mock_get = mocker.patch("httpx.get", return_value=mock_response)

    result = get_body("http://127.0.0.1/schema.json", allow_private_network=True)

    assert result == '{"type": "object"}'
    assert mock_get.call_count == 1


def test_get_body_blocks_hostname_resolving_to_unsafe_ip(mocker: MockerFixture) -> None:
    """Block hostnames that resolve to local or private network targets."""
    mocker.patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))],
    )
    mock_get = mocker.patch("httpx.get")

    with pytest.raises(SchemaFetchError, match="--allow-private-network"):
        get_body("https://metadata.example.com/schema.json")
    assert mock_get.call_count == 0


def test_get_body_blocks_redirect_to_unsafe_url(mocker: MockerFixture) -> None:
    """Validate redirect targets before the next request."""
    mock_response = Mock()
    mock_response.status_code = 302
    mock_response.headers = {"location": "http://127.0.0.1/schema.json"}
    mock_get = mocker.patch("httpx.get", return_value=mock_response)

    with pytest.raises(SchemaFetchError, match="--allow-private-network"):
        get_body("https://example.com/schema.json")
    assert mock_get.call_count == 1


def test_get_body_allows_redirect_to_unsafe_url_with_explicit_opt_in(mocker: MockerFixture) -> None:
    """Allow trusted redirects to private network targets only when explicitly requested."""
    redirect_response = Mock()
    redirect_response.status_code = 302
    redirect_response.headers = {"location": "http://127.0.0.1/schema.json"}
    success_response = Mock()
    success_response.status_code = 200
    success_response.headers = {"content-type": "application/json"}
    success_response.text = '{"type": "object"}'
    mock_get = mocker.patch("httpx.get", side_effect=[redirect_response, success_response])

    result = get_body("https://example.com/schema.json", allow_private_network=True)

    assert result == '{"type": "object"}'
    assert [call.args[0] for call in mock_get.call_args_list] == [
        "https://example.com/schema.json",
        "http://127.0.0.1/schema.json",
    ]


def test_get_body_follows_relative_redirect(mocker: MockerFixture) -> None:
    """Follow safe relative redirects."""
    redirect_response = Mock()
    redirect_response.status_code = 302
    redirect_response.headers = {"location": "schema.json"}
    success_response = Mock()
    success_response.status_code = 200
    success_response.headers = {"content-type": "application/json"}
    success_response.text = '{"type": "object"}'
    mock_get = mocker.patch("httpx.get", side_effect=[redirect_response, success_response])

    result = get_body(
        "https://example.com/schemas/root.json",
        query_parameters=[("version", "v2")],
    )

    assert result == '{"type": "object"}'
    assert [call.args[0] for call in mock_get.call_args_list] == [
        "https://example.com/schemas/root.json",
        "https://example.com/schemas/schema.json",
    ]
    assert mock_get.call_args_list[0].kwargs["params"] == [("version", "v2")]
    assert mock_get.call_args_list[1].kwargs["params"] is None


def test_get_body_strips_credentials_on_cross_origin_redirect(mocker: MockerFixture) -> None:
    """Do not forward scoped credentials to a different redirect origin."""
    mocker.patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))],
    )
    redirect_response = Mock()
    redirect_response.status_code = 302
    redirect_response.headers = {"location": "https://attacker.example.net/schema.json"}
    success_response = Mock()
    success_response.status_code = 200
    success_response.headers = {"content-type": "application/json"}
    success_response.text = '{"type": "object"}'
    mock_get = mocker.patch("httpx.get", side_effect=[redirect_response, success_response])
    headers = [
        ("Authorization", "Bearer secret"),
        ("Cookie", "session=secret"),
        ("Proxy-Authorization", "Basic secret"),
        ("X-Request-Id", "abc"),
    ]

    result = get_body("https://example.com/schema.json", headers=headers)

    assert result == '{"type": "object"}'
    assert [call.args[0] for call in mock_get.call_args_list] == [
        "https://example.com/schema.json",
        "https://attacker.example.net/schema.json",
    ]
    assert mock_get.call_args_list[0].kwargs["headers"] == headers
    assert mock_get.call_args_list[1].kwargs["headers"] == [("X-Request-Id", "abc")]


def test_get_body_keeps_headers_on_same_origin_redirect(mocker: MockerFixture) -> None:
    """Keep headers when a redirect stays on the same origin."""
    mocker.patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))],
    )
    redirect_response = Mock()
    redirect_response.status_code = 301
    redirect_response.headers = {"location": "https://EXAMPLE.com:443/schemas/other.json"}
    success_response = Mock()
    success_response.status_code = 200
    success_response.headers = {"content-type": "application/json"}
    success_response.text = '{"type": "object"}'
    mock_get = mocker.patch("httpx.get", side_effect=[redirect_response, success_response])
    headers = [("Authorization", "Bearer secret")]

    get_body("https://example.com/schemas/root.json", headers=headers)

    assert mock_get.call_args_list[1].kwargs["headers"] == headers


@pytest.mark.parametrize(
    ("current_url", "redirect_url", "expected"),
    [
        ("https://example.com/a", "https://example.com:443/b", [("Authorization", "x"), ("Accept", "y")]),
        ("https://example.com/a", "http://example.com/b", [("Accept", "y")]),
        ("https://example.com/a", "https://example.com:8443/b", [("Accept", "y")]),
        ("https://example.com/a", "https://other.example.com/b", [("Accept", "y")]),
        ("https://example.com/a", "https://example.com:bad/b", [("Accept", "y")]),
    ],
)
def test_get_redirect_headers(current_url: str, redirect_url: str, expected: list[tuple[str, str]]) -> None:
    """Strip scoped credentials unless the redirect keeps the same origin."""
    headers = [("Authorization", "x"), ("Accept", "y")]
    assert _get_redirect_headers(headers, current_url, redirect_url) == expected
    assert _get_redirect_headers(None, current_url, redirect_url) is None
    mapping_result = _get_redirect_headers(dict(headers), current_url, redirect_url)  # ty: ignore
    assert dict(mapping_result or {}) == dict(expected)


def test_get_url_origin() -> None:
    """Normalize scheme, host, and default port for origin comparison."""
    assert _get_url_origin("HTTPS://Example.COM./x") == ("https", "example.com", 443)
    assert _get_url_origin("http://example.com:8080/x") == ("http", "example.com", 8080)
    assert _get_url_origin("https:///x") is None
    assert _get_url_origin("https://example.com:bad/x") is None


@pytest.mark.parametrize("url", ["ftp://example.com/schema.json", "https:///schema.json"])
def test_get_body_rejects_invalid_fetch_urls(mocker: MockerFixture, url: str) -> None:
    """Reject unsupported or incomplete URLs before fetching."""
    mock_get = mocker.patch("httpx.get")

    with pytest.raises(SchemaFetchError, match="HTTP fetch"):
        get_body(url)
    assert mock_get.call_count == 0


def test_get_body_rejects_redirect_without_location(mocker: MockerFixture) -> None:
    """Reject redirect responses that do not provide a target."""
    mock_response = Mock()
    mock_response.status_code = 302
    mock_response.headers = {}
    mock_get = mocker.patch("httpx.get", return_value=mock_response)

    with pytest.raises(SchemaFetchError, match="missing a Location header"):
        get_body("https://example.com/schema.json")
    assert mock_get.call_count == 1


def test_get_body_rejects_too_many_redirects(mocker: MockerFixture) -> None:
    """Reject redirect chains that exceed the configured limit."""
    mock_response = Mock()
    mock_response.status_code = 302
    mock_response.headers = {"location": "https://example.com/schema.json"}
    mock_get = mocker.patch("httpx.get", return_value=mock_response)

    with pytest.raises(SchemaFetchError, match="Too many redirects"):
        get_body("https://example.com/schema.json")
    assert mock_get.call_count == MAX_HTTP_REDIRECTS + 1


def test_get_body_wraps_transport_error(mocker: MockerFixture) -> None:
    """Test that transport failures (DNS, timeout, etc.) are wrapped in SchemaFetchError."""
    import httpx

    mocker.patch("httpx.get", side_effect=httpx.ConnectError("DNS resolution failed"))

    with pytest.raises(SchemaFetchError, match="Failed to fetch"):
        get_body("https://nonexistent.example.com/schema.json")
