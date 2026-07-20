import sys

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The corrupted block we want to find and replace
bad_block = """def _parse_args() -> argparse.Namespace:
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
        default=False,"""

good_block = """def _parse_args() -> argparse.Namespace:
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
    return parser.parse_args()"""

if bad_block in content:
    idx = content.find(bad_block)
    end_idx = content.find("if __name__ == \"__main__\":", idx)
    
    new_content = content[:idx] + good_block + "\n\n\n" + content[end_idx:]
    
    with open('main.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Fixed main.py")
else:
    print("Bad block not found. Maybe it's slightly different?")
