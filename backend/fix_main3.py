import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# find the FIRST `# CLI entry point`
idx = content.find("# CLI entry point")

# find `if __name__ == "__main__":`
end_idx = content.find("if __name__ == \"__main__\":")

good_block = """# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pollinator Ecosystem Analysis Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--zone_id", required=True, help="Unique zone identifier")
    parser.add_argument("--lat",     required=True, type=float, help="Latitude (decimal degrees)")
    parser.add_argument("--lon",     required=True, type=float, help="Longitude (decimal degrees)")
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=False,
        help="Pretty-print the JSON output (indent=2)",
    )
    return parser.parse_args()


"""

new_content = content[:idx] + good_block + content[end_idx:]

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Fixed")
