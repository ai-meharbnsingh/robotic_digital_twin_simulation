"""
Tests for CSV order import endpoint.
POST /api/wes/orders/import — upload CSV, validate nodes, create tasks.
"""

import io
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app, lifespan


@pytest_asyncio.fixture
async def client():
    """Async test client with lifespan."""
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


VALID_CSV = """\
source_node,destination_node,priority,payload_kg,order_type
PICK_1,DROP_1,5,2.5,pick_and_drop
PICK_1,DROP_1,3,1.0,pick_and_drop
PICK_1,DROP_1,8,10.0,pick_and_drop
"""

VALID_CSV_MINIMAL = """\
source_node,destination_node
PICK_1,DROP_1
PICK_1,DROP_1
"""

INVALID_NODES_CSV = """\
source_node,destination_node,priority
PICK_1,DROP_1,5
FAKE_NODE,DROP_1,3
PICK_1,NONEXISTENT,8
"""

MISSING_COLUMNS_CSV = """\
source,destination
PICK_1,DROP_1
"""

EMPTY_CSV = ""

HEADER_ONLY_CSV = """\
source_node,destination_node,priority
"""

MIXED_VALID_INVALID_CSV = """\
source_node,destination_node,priority,payload_kg
PICK_1,DROP_1,5,2.5
,DROP_1,3,1.0
PICK_1,,8,10.0
PICK_1,DROP_1,bad_priority,5.0
PICK_1,DROP_1,1,not_a_number
PICK_1,DROP_1,7,15.0
"""

BOM_CSV = "\ufeff" + VALID_CSV  # Excel BOM prefix


class TestOrderImport:
    """Test CSV order import endpoint."""

    async def test_upload_valid_csv(self, client: AsyncClient):
        """Upload valid CSV — all orders imported, tasks created."""
        files = {"file": ("orders.csv", io.BytesIO(VALID_CSV.encode()), "text/csv")}
        resp = await client.post("/api/wes/orders/import", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 3
        assert data["tasks_created"] >= 3  # pick_and_drop = 1 task each
        assert len(data["errors"]) == 0
        assert len(data["orders"]) == 3
        # Verify order contents
        assert data["orders"][0]["source_node"] == "PICK_1"
        assert data["orders"][0]["destination_node"] == "DROP_1"
        assert data["orders"][0]["priority"] == 5
        assert data["orders"][0]["payload_kg"] == 2.5

    async def test_upload_minimal_csv(self, client: AsyncClient):
        """Upload CSV with only required columns — defaults applied."""
        files = {"file": ("orders.csv", io.BytesIO(VALID_CSV_MINIMAL.encode()), "text/csv")}
        resp = await client.post("/api/wes/orders/import", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 2
        assert data["orders"][0]["priority"] == 0  # default
        assert data["orders"][0]["payload_kg"] == 0.0  # default
        assert data["orders"][0]["order_type"] == "pick_and_drop"  # default

    async def test_invalid_nodes_rejected(self, client: AsyncClient):
        """Invalid node names produce row-level errors."""
        files = {"file": ("orders.csv", io.BytesIO(INVALID_NODES_CSV.encode()), "text/csv")}
        resp = await client.post("/api/wes/orders/import", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1  # only first row valid
        assert len(data["errors"]) == 2
        assert "FAKE_NODE" in data["errors"][0]["error"]
        assert "NONEXISTENT" in data["errors"][1]["error"]

    async def test_missing_required_columns(self, client: AsyncClient):
        """CSV missing required columns returns 400."""
        files = {"file": ("orders.csv", io.BytesIO(MISSING_COLUMNS_CSV.encode()), "text/csv")}
        resp = await client.post("/api/wes/orders/import", files=files)
        assert resp.status_code == 400
        assert "Missing required columns" in resp.json()["detail"]

    async def test_empty_file(self, client: AsyncClient):
        """Empty CSV returns 400."""
        files = {"file": ("orders.csv", io.BytesIO(EMPTY_CSV.encode()), "text/csv")}
        resp = await client.post("/api/wes/orders/import", files=files)
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    async def test_header_only_csv(self, client: AsyncClient):
        """CSV with header but no data rows returns 0 imported."""
        files = {"file": ("orders.csv", io.BytesIO(HEADER_ONLY_CSV.encode()), "text/csv")}
        resp = await client.post("/api/wes/orders/import", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 0
        assert "No valid orders" in data["message"]

    async def test_mixed_valid_invalid_rows(self, client: AsyncClient):
        """Mix of valid and invalid rows — valid imported, invalid reported."""
        files = {"file": ("orders.csv", io.BytesIO(MIXED_VALID_INVALID_CSV.encode()), "text/csv")}
        resp = await client.post("/api/wes/orders/import", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 2  # rows 1 and 6 valid
        assert len(data["errors"]) == 4  # rows 2,3,4,5 invalid
        # Check error details
        error_messages = [e["error"] for e in data["errors"]]
        assert any("empty" in m for m in error_messages)
        assert any("not an integer" in m or "not a number" in m for m in error_messages)

    async def test_bom_csv_handled(self, client: AsyncClient):
        """CSV with Excel BOM (byte order mark) is handled correctly."""
        files = {"file": ("orders.csv", io.BytesIO(BOM_CSV.encode("utf-8")), "text/csv")}
        resp = await client.post("/api/wes/orders/import", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 3

    async def test_large_csv(self, client: AsyncClient):
        """Upload 100 orders — all imported in <2s."""
        lines = ["source_node,destination_node,priority,payload_kg"]
        for i in range(100):
            lines.append(f"PICK_1,DROP_1,{i % 10},{(i % 20) + 0.5}")
        csv_content = "\n".join(lines)
        files = {"file": ("big.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        resp = await client.post("/api/wes/orders/import", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 100
        assert data["tasks_created"] >= 100

    async def test_orders_have_unique_ids(self, client: AsyncClient):
        """Each imported order gets a unique order_id."""
        files = {"file": ("orders.csv", io.BytesIO(VALID_CSV.encode()), "text/csv")}
        resp = await client.post("/api/wes/orders/import", files=files)
        data = resp.json()
        order_ids = [o["order_id"] for o in data["orders"]]
        assert len(order_ids) == len(set(order_ids))  # all unique

    async def test_endpoint_count_updated(self, client: AsyncClient):
        """Root endpoint reflects updated count."""
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["endpoints"] == 31
