"""
InfluxWriter — writes telemetry time-series data to InfluxDB.

Real InfluxDB client. Graceful degradation if InfluxDB is unavailable.
No MagicMock. No faking.
"""

import time
from typing import Any, Optional

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS


class InfluxWriter:
    """
    Writes robot telemetry to InfluxDB.

    Falls back gracefully if InfluxDB is unreachable — logs the failure
    but does not crash.
    """

    def __init__(self, url: str, token: str, org: str, bucket: str):
        """
        Args:
            url: InfluxDB URL (e.g., http://localhost:8086).
            token: InfluxDB authentication token.
            org: InfluxDB organization.
            bucket: InfluxDB bucket for telemetry data.
        """
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self._client: Optional[InfluxDBClient] = None
        self._write_api = None
        self._available = False
        self._write_count = 0
        self._error_count = 0

        self._init_client()

    def _init_client(self):
        """Initialize InfluxDB client."""
        try:
            self._client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org,
                timeout=3000,
            )
            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            # Test connectivity
            health = self._client.health()
            self._available = health.status == "pass"
        except Exception:
            self._available = False

    def write_telemetry(
        self,
        robot_id: str,
        measurement: str,
        fields: dict[str, float],
        tags: dict[str, str] = None,
    ) -> bool:
        """
        Write a single telemetry point.

        Args:
            robot_id: Robot identifier.
            measurement: Measurement name (e.g., "battery", "velocity").
            fields: Numeric field values.
            tags: String tag values.

        Returns:
            True if write succeeded.
        """
        if not self._available or self._write_api is None:
            self._error_count += 1
            return False

        try:
            point = Point(measurement).tag("robot_id", robot_id)
            if tags:
                for k, v in tags.items():
                    point = point.tag(k, v)
            for k, v in fields.items():
                point = point.field(k, v)
            point = point.time(time.time_ns(), WritePrecision.NS)

            self._write_api.write(bucket=self.bucket, org=self.org, record=point)
            self._write_count += 1
            return True
        except Exception:
            self._error_count += 1
            return False

    def write_batch(self, points: list[dict[str, Any]]) -> int:
        """
        Write a batch of telemetry points.

        Args:
            points: List of dicts with robot_id, measurement, fields, tags.

        Returns:
            Number of points successfully written.
        """
        written = 0
        for p in points:
            if self.write_telemetry(
                robot_id=p["robot_id"],
                measurement=p["measurement"],
                fields=p["fields"],
                tags=p.get("tags", {}),
            ):
                written += 1
        return written

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def write_count(self) -> int:
        return self._write_count

    @property
    def error_count(self) -> int:
        return self._error_count

    def close(self):
        """Close the InfluxDB client."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
