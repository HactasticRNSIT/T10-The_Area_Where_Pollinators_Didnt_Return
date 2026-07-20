import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace everything from the first '# CLI entry point' to 'if __name__ == "__main__":'
pattern = re.compile(r'# CLI entry point.*?if __name__ == "__main__":', re.DOTALL)

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


if __name__ == "__main__":"""

new_content, count = pattern.subn(good_block, content)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"Replaced {count} occurrences.")
