"""Render the Phase 2 service cutover plan from the repository manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.check_service_environment import (
    format_validation_result,
    load_project_dotenv,
    validate_environment,
)


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "migrations" / "cutover_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render the Phase 2 cutover checklist")
    parser.add_argument(
        "services",
        nargs="*",
        help="Subset of services to include; defaults to the full execution order",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="Run service environment validation for the selected services before printing the plan",
    )
    return parser


def render_text(manifest: dict, selected_services: list[str]) -> str:
    services = {
        entry["service"]: entry
        for entry in manifest["services"]
        if entry["service"] in selected_services
    }
    lines = [
        "Phase 2 Cutover Plan",
        "",
        "Execution order:",
        " -> ".join(selected_services),
    ]
    for service_name in selected_services:
        entry = services[service_name]
        lines.extend(
            [
                "",
                f"{entry['order']}. {service_name}",
                f"   database env: {entry['database_env']}",
                f"   migration namespace: {entry['migration_namespace']}",
                f"   schema snapshot: {entry['schema_snapshot']}",
                f"   owned tables: {', '.join(entry['owned_tables'])}",
            ]
        )
        if entry["owned_views"]:
            lines.append(f"   owned views: {', '.join(entry['owned_views'])}")
        if entry["internal_dependencies"]:
            lines.append(
                f"   internal dependencies: {', '.join(entry['internal_dependencies'])}"
            )
        if entry["external_reference_columns"]:
            refs = ", ".join(
                f"{table}({', '.join(columns)})"
                for table, columns in entry["external_reference_columns"].items()
            )
            lines.append(f"   external references: {refs}")
        lines.append("   preconditions:")
        lines.extend(f"   - {item}" for item in entry["preconditions"])
        lines.append("   post-cutover checks:")
        lines.extend(f"   - {item}" for item in entry["post_cutover_checks"])
    return "\n".join(lines)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    load_project_dotenv()

    manifest = load_manifest()
    available = manifest["execution_order"]
    selected_services = args.services or available

    unknown = [service for service in selected_services if service not in available]
    if unknown:
        parser.error(f"Unknown services: {', '.join(sorted(unknown))}")

    if args.check_env:
        validation = validate_environment(selected_services)
        print(format_validation_result(validation))
        if not validation.ok:
            raise SystemExit(1)
        print("")

    if args.format == "json":
        filtered = {
            "version": manifest["version"],
            "execution_order": selected_services,
            "services": [
                entry for entry in manifest["services"] if entry["service"] in selected_services
            ],
        }
        print(json.dumps(filtered, ensure_ascii=False, indent=2))
        return

    print(render_text(manifest, selected_services))


if __name__ == "__main__":
    main()
