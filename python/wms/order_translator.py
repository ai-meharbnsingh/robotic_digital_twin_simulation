"""
Order Translator — converts between WMS-specific and internal order formats.

Internal order format:
{
    "order_id": str,
    "source": "sap" | "odoo" | "webhook",
    "items": [{"sku": str, "quantity": int, "location": str}],
    "priority": int (1-5, 1=highest),
    "customer": str,
    "created_at": str (ISO 8601),
    "raw": dict (original payload preserved),
}
"""

import time


class OrderTranslator:
    """Translates between WMS-specific and internal order formats."""

    @staticmethod
    def from_sap(sap_order: dict) -> dict:
        """SAP AUFNR/MATNR/WERKS -> internal order.

        SAP fields:
            AUFNR = order number
            MATNR = material number (SKU)
            WERKS = plant code
            LGORT = storage location
            MENGE = quantity
            KUNNR = customer number
            PRIOK = priority key
        """
        items = []
        for line in sap_order.get("items", sap_order.get("POSNR", [])):
            if isinstance(line, dict):
                items.append({
                    "sku": line.get("MATNR", line.get("sku", "")),
                    "quantity": int(line.get("MENGE", line.get("quantity", 1))),
                    "location": line.get("LGORT", line.get("location", "")),
                })

        return {
            "order_id": sap_order.get("AUFNR", sap_order.get("order_id", "")),
            "source": "sap",
            "items": items,
            "priority": int(sap_order.get("PRIOK", sap_order.get("priority", 3))),
            "customer": sap_order.get("KUNNR", sap_order.get("customer", "")),
            "created_at": sap_order.get("ERDAT", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            "raw": sap_order,
        }

    @staticmethod
    def from_odoo(odoo_order: dict) -> dict:
        """Odoo sale.order -> internal order.

        Odoo fields:
            name = order reference (e.g. SO001)
            partner_id = customer [id, name]
            order_line = line items
            state = sale/done/cancel
            date_order = order date
        """
        items = []
        for line in odoo_order.get("order_line", []):
            if isinstance(line, dict):
                # Full dict line object — extract product_id which can be
                # [id, name] tuple or a bare string/int
                pid = line.get("product_id", "")
                if isinstance(pid, (list, tuple)) and len(pid) > 1:
                    sku = str(pid[1])
                else:
                    sku = str(pid)
                items.append({
                    "sku": sku,
                    "quantity": int(line.get("product_uom_qty", line.get("quantity", 1))),
                    "location": line.get("warehouse_id", ""),
                })
            elif isinstance(line, (int, float)):
                # Odoo sometimes returns order_line as a list of IDs only
                # (when fields aren't expanded). We can't extract product
                # data from bare IDs so we create a placeholder item.
                items.append({
                    "sku": f"odoo-line-{int(line)}",
                    "quantity": 1,
                    "location": "",
                })

        partner = odoo_order.get("partner_id", [0, ""])
        customer = partner[1] if isinstance(partner, list) and len(partner) > 1 else str(partner)

        return {
            "order_id": odoo_order.get("name", ""),
            "source": "odoo",
            "items": items,
            "priority": 3,  # Odoo doesn't have a standard priority on sale.order
            "customer": customer,
            "created_at": odoo_order.get("date_order", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            "raw": odoo_order,
        }

    @staticmethod
    def from_webhook(webhook_payload: dict) -> dict:
        """Generic webhook -> internal order.

        Expected webhook fields (flexible):
            id or order_id = order identifier
            items = list of {sku, quantity, location}
            priority = 1-5
            customer = customer name
        """
        items = []
        for line in webhook_payload.get("items", []):
            if isinstance(line, dict):
                items.append({
                    "sku": line.get("sku", ""),
                    "quantity": int(line.get("quantity", 1)),
                    "location": line.get("location", ""),
                })

        return {
            "order_id": webhook_payload.get("id", webhook_payload.get("order_id", webhook_payload.get("_internal_id", ""))),
            "source": "webhook",
            "items": items,
            "priority": int(webhook_payload.get("priority", 3)),
            "customer": webhook_payload.get("customer", ""),
            "created_at": webhook_payload.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            "raw": webhook_payload,
        }

    @staticmethod
    def to_internal(source: str, raw_order: dict) -> dict:
        """Auto-detect source and translate.

        Args:
            source: One of 'sap', 'odoo', 'webhook'.
            raw_order: Raw order dict from the WMS.

        Returns:
            Internal order format.

        Raises:
            ValueError: If source is unknown.
        """
        translators = {
            "sap": OrderTranslator.from_sap,
            "odoo": OrderTranslator.from_odoo,
            "webhook": OrderTranslator.from_webhook,
        }
        translator = translators.get(source)
        if translator is None:
            raise ValueError(f"Unknown WMS source: {source!r}. Supported: {list(translators.keys())}")
        return translator(raw_order)
