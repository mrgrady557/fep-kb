from bs4 import BeautifulSoup
from pathlib import Path
import re


# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

SAMPLES_DIR = Path("samples")
HTML_FILES = sorted(SAMPLES_DIR.glob("INC*.html"))

if not HTML_FILES:
    raise RuntimeError("No INC*.html files found in samples/")


KB_TYPES = {
    "Internal Work notes",
    "Additional comments"
}


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def normalize_type(label: str) -> str:
    """
    Strip timestamps and relative-time text from activity labels.
    """
    return label.split("•")[0].strip()


def clean_public_content(text: str) -> str:
    """
    Clean public-facing comments for KB use.
    Internal notes are intentionally NOT passed here.
    """

    lines = text.splitlines()
    cleaned_lines = []

    STOP_MARKERS = [
        "--",
        "All electronic mail messages",
        "Public Records Law",
        "Schedule a",
        "Professor and",
        "College of",
        "Department of",
        "North Carolina State University",
        "Campus Box"
    ]

    HEADER_PATTERNS = [
        r"^reply from:",
        r"^received from:"
    ]

    for line in lines:
        stripped = line.strip()

        # Stop if we hit a signature / boilerplate section
        if any(marker.lower() in stripped.lower() for marker in STOP_MARKERS):
            break

        # Skip email-style headers
        if any(re.match(pat, stripped.lower()) for pat in HEADER_PATTERNS):
            continue

        cleaned_lines.append(stripped)

    # Rejoin and normalize spacing
    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

    return cleaned_text.strip()



def parse_ticket(html_file: Path) -> list[dict]:
    """
    Parse a single ServiceNow ticket HTML file and return KB entries.
    """

    ticket_id = html_file.stem  # e.g. INC4555644

    with open(html_file, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")

    # Locate activity stream
    streams = soup.find_all("div", class_="sn-stream")

    activity_stream = None
    for stream in streams:
        if stream.find("div", class_="sn-card-component"):
            activity_stream = stream
            break

    if not activity_stream:
        return []

    cards = activity_stream.find_all("div", class_="sn-card-component")

    activities = []
    current_activity = None

    for card in cards:

        # -----------------------------------------------------------
        # AUTHOR CARD
        # -----------------------------------------------------------
        author = card.find("span", class_="sn-card-component-createdby")
        if author:
            if current_activity:
                current_activity["content"] = "\n\n".join(current_activity["content"])
                activities.append(current_activity)

            current_activity = {
                "ticket_id": ticket_id,
                "author": author.get_text(strip=True),
                "type": None,
                "timestamp": None,
                "visibility": None,
                "content": []
            }
            continue

        # -----------------------------------------------------------
        # TYPE + TIMESTAMP CARD
        # -----------------------------------------------------------
        time_block = card.find("div", class_="date-calendar")
        if time_block and current_activity:
            raw_label = card.get_text(" ", strip=True)
            activity_type = normalize_type(raw_label)

            current_activity["type"] = activity_type
            current_activity["timestamp"] = time_block.get_text(strip=True)
            current_activity["visibility"] = (
                "internal" if activity_type == "Internal Work notes" else "public"
            )
            continue

        # -----------------------------------------------------------
        # CONTENT CARDS
        # -----------------------------------------------------------
        if not current_activity:
            continue

        card_classes = card.get("class", [])

        # Field changes / record-style content
        if "sn-card-component_records" in card_classes:
            current_activity["content"].append(
                card.get_text("\n", strip=True)
            )
            continue

        # Comment / work note summary
        summary = card.find("div", class_="sn-card-component_summary")
        if summary:
            current_activity["content"].append(
                summary.get_text("\n", strip=True)
            )
            continue

        # Rich text editor fallback
        rich_text = card.find("div", class_="sn-widget-textblock")
        if rich_text:
            current_activity["content"].append(
                rich_text.get_text("\n", strip=True)
            )
            continue

    # Append final activity
    if current_activity:
        content = "\n\n".join(current_activity["content"])

        if current_activity["visibility"] == "public":
            content = clean_public_content(content)

        current_activity["content"] = content
        activities.append(current_activity)


    # Filter to KB-worthy entries
    kb_entries = [
        a for a in activities
        if a["type"] in KB_TYPES and a["content"].strip()
    ]

    return kb_entries


# -------------------------------------------------------------------
# Batch parse all tickets
# -------------------------------------------------------------------

all_kb_entries = []

print(f"Found {len(HTML_FILES)} ticket files\n")

for html_file in HTML_FILES:
    entries = parse_ticket(html_file)
    all_kb_entries.extend(entries)
    print(f"{html_file.stem}: {len(entries)} KB entries")


# -------------------------------------------------------------------
# Summary preview
# -------------------------------------------------------------------

print("\n=== BATCH SUMMARY ===")
print(f"Tickets processed : {len(HTML_FILES)}")
print(f"KB entries found  : {len(all_kb_entries)}")

print("\n=== SAMPLE KB ENTRIES ===")

for entry in all_kb_entries[:5]:
    print("\n--- KB ENTRY ---")
    print(f"Ticket     : {entry['ticket_id']}")
    print(f"Author     : {entry['author']}")
    print(f"Visibility : {entry['visibility']}")
    print(f"Timestamp  : {entry['timestamp']}")
    print("Content:")
    print(entry["content"])
