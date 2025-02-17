"""Test the webhook component."""
from http import HTTPStatus
from ipaddress import ip_address
from unittest.mock import patch

from aiohttp import web
import pytest

from homeassistant.components import webhook
from homeassistant.config import async_process_ha_core_config
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


@pytest.fixture
def mock_client(hass, hass_client):
    """Create http client for webhooks."""
    hass.loop.run_until_complete(async_setup_component(hass, "webhook", {}))
    return hass.loop.run_until_complete(hass_client())


async def test_unregistering_webhook(hass, mock_client):
    """Test unregistering a webhook."""
    hooks = []
    webhook_id = webhook.async_generate_id()

    async def handle(*args):
        """Handle webhook."""
        hooks.append(args)

    webhook.async_register(hass, "test", "Test hook", webhook_id, handle)

    resp = await mock_client.post(f"/api/webhook/{webhook_id}")
    assert resp.status == HTTPStatus.OK
    assert len(hooks) == 1

    webhook.async_unregister(hass, webhook_id)

    resp = await mock_client.post(f"/api/webhook/{webhook_id}")
    assert resp.status == HTTPStatus.OK
    assert len(hooks) == 1


async def test_generate_webhook_url(hass: HomeAssistant) -> None:
    """Test we generate a webhook url correctly."""
    await async_process_ha_core_config(
        hass,
        {"external_url": "https://example.com"},
    )
    url = webhook.async_generate_url(hass, "some_id")

    assert url == "https://example.com/api/webhook/some_id"


async def test_async_generate_path(hass: HomeAssistant) -> None:
    """Test generating just the path component of the url correctly."""
    path = webhook.async_generate_path("some_id")
    assert path == "/api/webhook/some_id"


async def test_posting_webhook_nonexisting(hass, mock_client):
    """Test posting to a nonexisting webhook."""
    resp = await mock_client.post("/api/webhook/non-existing")
    assert resp.status == HTTPStatus.OK


async def test_posting_webhook_invalid_json(hass, mock_client):
    """Test posting to a nonexisting webhook."""
    webhook.async_register(hass, "test", "Test hook", "hello", None)
    resp = await mock_client.post("/api/webhook/hello", data="not-json")
    assert resp.status == HTTPStatus.OK


async def test_posting_webhook_json(hass, mock_client):
    """Test posting a webhook with JSON data."""
    hooks = []
    webhook_id = webhook.async_generate_id()

    async def handle(*args):
        """Handle webhook."""
        hooks.append((args[0], args[1], await args[2].text()))

    webhook.async_register(hass, "test", "Test hook", webhook_id, handle)

    resp = await mock_client.post(f"/api/webhook/{webhook_id}", json={"data": True})
    assert resp.status == HTTPStatus.OK
    assert len(hooks) == 1
    assert hooks[0][0] is hass
    assert hooks[0][1] == webhook_id
    assert hooks[0][2] == '{"data": true}'


async def test_posting_webhook_no_data(hass, mock_client):
    """Test posting a webhook with no data."""
    hooks = []
    webhook_id = webhook.async_generate_id()

    async def handle(*args):
        """Handle webhook."""
        hooks.append(args)

    webhook.async_register(hass, "test", "Test hook", webhook_id, handle)

    resp = await mock_client.post(f"/api/webhook/{webhook_id}")
    assert resp.status == HTTPStatus.OK
    assert len(hooks) == 1
    assert hooks[0][0] is hass
    assert hooks[0][1] == webhook_id
    assert hooks[0][2].method == "POST"
    assert await hooks[0][2].text() == ""


async def test_webhook_put(hass, mock_client):
    """Test sending a put request to a webhook."""
    hooks = []
    webhook_id = webhook.async_generate_id()

    async def handle(*args):
        """Handle webhook."""
        hooks.append(args)

    webhook.async_register(hass, "test", "Test hook", webhook_id, handle)

    resp = await mock_client.put(f"/api/webhook/{webhook_id}")
    assert resp.status == HTTPStatus.OK
    assert len(hooks) == 1
    assert hooks[0][0] is hass
    assert hooks[0][1] == webhook_id
    assert hooks[0][2].method == "PUT"


async def test_webhook_head(hass, mock_client):
    """Test sending a head request to a webhook."""
    hooks = []
    webhook_id = webhook.async_generate_id()

    async def handle(*args):
        """Handle webhook."""
        hooks.append(args)

    webhook.async_register(hass, "test", "Test hook", webhook_id, handle)

    resp = await mock_client.head(f"/api/webhook/{webhook_id}")
    assert resp.status == HTTPStatus.OK
    assert len(hooks) == 1
    assert hooks[0][0] is hass
    assert hooks[0][1] == webhook_id
    assert hooks[0][2].method == "HEAD"


async def test_webhook_local_only(hass, mock_client):
    """Test posting a webhook with local only."""
    hooks = []
    webhook_id = webhook.async_generate_id()

    async def handle(*args):
        """Handle webhook."""
        hooks.append((args[0], args[1], await args[2].text()))

    webhook.async_register(
        hass, "test", "Test hook", webhook_id, handle, local_only=True
    )

    resp = await mock_client.post(f"/api/webhook/{webhook_id}", json={"data": True})
    assert resp.status == HTTPStatus.OK
    assert len(hooks) == 1
    assert hooks[0][0] is hass
    assert hooks[0][1] == webhook_id
    assert hooks[0][2] == '{"data": true}'

    # Request from remote IP
    with patch(
        "homeassistant.components.webhook.ip_address",
        return_value=ip_address("123.123.123.123"),
    ):
        resp = await mock_client.post(f"/api/webhook/{webhook_id}", json={"data": True})
    assert resp.status == HTTPStatus.OK
    # No hook received
    assert len(hooks) == 1


async def test_listing_webhook(
    hass, hass_ws_client, hass_access_token, enable_custom_integrations
):
    """Test unregistering a webhook."""
    assert await async_setup_component(hass, "webhook", {})
    client = await hass_ws_client(hass, hass_access_token)

    webhook.async_register(hass, "test", "Test hook", "my-id", None)
    webhook.async_register(hass, "test", "Test hook", "my-2", None, local_only=True)

    await client.send_json({"id": 5, "type": "webhook/list"})

    msg = await client.receive_json()
    assert msg["id"] == 5
    assert msg["success"]
    assert msg["result"] == [
        {
            "webhook_id": "my-id",
            "domain": "test",
            "name": "Test hook",
            "local_only": False,
        },
        {
            "webhook_id": "my-2",
            "domain": "test",
            "name": "Test hook",
            "local_only": True,
        },
    ]


async def test_ws_webhook(hass, caplog, hass_ws_client):
    """Test sending webhook msg via WS API."""
    assert await async_setup_component(hass, "webhook", {})

    received = []

    async def handler(hass, webhook_id, request):
        """Handle a webhook."""
        received.append(request)
        return web.json_response({"from": "handler"})

    webhook.async_register(hass, "test", "Test", "mock-webhook-id", handler)

    client = await hass_ws_client(hass)

    await client.send_json(
        {
            "id": 5,
            "type": "webhook/handle",
            "webhook_id": "mock-webhook-id",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": '{"hello": "world"}',
            "query": "a=2",
        }
    )

    result = await client.receive_json()
    assert result["success"], result
    assert result["result"] == {
        "status": 200,
        "body": '{"from": "handler"}',
        "headers": {"Content-Type": "application/json"},
    }

    assert len(received) == 1
    assert received[0].headers["content-type"] == "application/json"
    assert received[0].query == {"a": "2"}
    assert await received[0].json() == {"hello": "world"}

    # Non existing webhook
    caplog.clear()

    await client.send_json(
        {
            "id": 6,
            "type": "webhook/handle",
            "webhook_id": "mock-nonexisting-id",
            "method": "POST",
            "body": '{"nonexisting": "payload"}',
        }
    )

    result = await client.receive_json()
    assert result["success"], result
    assert result["result"] == {
        "status": 200,
        "body": None,
        "headers": {"Content-Type": "application/octet-stream"},
    }

    assert (
        "Received message for unregistered webhook mock-nonexisting-id from webhook/ws"
        in caplog.text
    )
    assert '{"nonexisting": "payload"}' in caplog.text
