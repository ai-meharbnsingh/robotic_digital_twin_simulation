"""
ReportGenerator — CSV and PDF export for scenario comparisons.

Phase 6: Parallel Scenario Comparison.
"""

import csv
import html
import io

# Characters that trigger formula execution in spreadsheet applications (OWASP).
_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_csv_value(value: str) -> str:
    """Strip CSV formula injection prefixes (OWASP recommendation).

    Same pattern as order_import._sanitize_csv_value().
    """
    if value and value[0] in _CSV_INJECTION_PREFIXES:
        return value.lstrip("=+\\-@\t\r")
    return value


def _sanitize_pdf_text(value: str) -> str:
    """Escape HTML/script content for safe insertion into reportlab Paragraphs/cells."""
    return html.escape(str(value), quote=True)


class ReportGenerator:
    """Generates CSV and PDF reports from scenario comparison data."""

    @staticmethod
    def generate_csv(comparison: dict) -> str:
        """
        Generate CSV report from comparison data.

        Args:
            comparison: Dict from ScenarioManager.compare_scenarios().

        Returns:
            CSV string with columns: metric, scenario_A_name, scenario_A_value, ...
        """
        scenarios = comparison.get("scenarios", [])
        if not scenarios:
            return "metric\n"

        # Collect all KPI metric names from the first scenario
        all_metrics = list(scenarios[0].get("kpis", {}).keys())

        output = io.StringIO()
        writer = csv.writer(output)

        # Header: metric, then each scenario name (sanitized against formula injection)
        header = ["metric"]
        for s in scenarios:
            name = s.get("name", s.get("scenario_id", "unknown"))
            header.append(_sanitize_csv_value(str(name)))
        writer.writerow(header)

        # One row per metric
        for metric in all_metrics:
            row = [_sanitize_csv_value(str(metric))]
            for s in scenarios:
                val = s.get("kpis", {}).get(metric, "")
                row.append(_sanitize_csv_value(str(val)))
            writer.writerow(row)

        return output.getvalue()

    @staticmethod
    def generate_pdf(comparison: dict) -> bytes:
        """
        Generate PDF report from comparison data.

        Args:
            comparison: Dict from ScenarioManager.compare_scenarios().

        Returns:
            PDF bytes.
        """
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate,
            Table,
            TableStyle,
            Paragraph,
            Spacer,
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        # Title
        elements.append(Paragraph("Scenario Comparison Report", styles["Title"]))
        elements.append(Spacer(1, 10 * mm))

        scenarios = comparison.get("scenarios", [])
        if not scenarios:
            elements.append(Paragraph("No scenarios to compare.", styles["Normal"]))
            doc.build(elements)
            return buffer.getvalue()

        # Config table
        elements.append(Paragraph("Configuration", styles["Heading2"]))
        config_header = ["Parameter"] + [_sanitize_pdf_text(s.get("name", "?")) for s in scenarios]
        config_data = [config_header]
        # Show key config params
        config_keys = ["fleet_size", "allocation_strategy", "order_count", "duration_s"]
        for key in config_keys:
            row = [_sanitize_pdf_text(key)]
            for s in scenarios:
                val = s.get("config", {}).get(key, "")
                row.append(_sanitize_pdf_text(str(val)))
            config_data.append(row)

        config_table = Table(config_data)
        config_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
        ]))
        elements.append(config_table)
        elements.append(Spacer(1, 10 * mm))

        # KPI comparison table
        elements.append(Paragraph("KPI Comparison", styles["Heading2"]))
        all_metrics = list(scenarios[0].get("kpis", {}).keys())
        kpi_header = ["Metric"] + [_sanitize_pdf_text(s.get("name", "?")) for s in scenarios]
        kpi_data = [kpi_header]
        for metric in all_metrics:
            row = [_sanitize_pdf_text(metric)]
            for s in scenarios:
                val = s.get("kpis", {}).get(metric, "")
                row.append(_sanitize_pdf_text(str(val)))
            kpi_data.append(row)

        kpi_table = Table(kpi_data)
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
        ]))
        elements.append(kpi_table)
        elements.append(Spacer(1, 10 * mm))

        # Rankings
        rankings = comparison.get("rankings", [])
        if rankings:
            elements.append(Paragraph("Rankings (by throughput)", styles["Heading2"]))
            rank_header = ["Rank", "Name", "Throughput (items/hr)", "Avg Cycle Time (s)"]
            rank_data = [rank_header]
            for r in rankings:
                rank_data.append([
                    _sanitize_pdf_text(str(r["rank"])),
                    _sanitize_pdf_text(r["name"]),
                    _sanitize_pdf_text(str(r["throughput_items_per_hour"])),
                    _sanitize_pdf_text(str(r["avg_order_cycle_time_s"])),
                ])
            rank_table = Table(rank_data)
            rank_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(rank_table)

        doc.build(elements)
        return buffer.getvalue()
