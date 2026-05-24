import os
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
BACKUPS_DIR = os.path.expanduser("~/zurg/backups")
INDEX_LOG_PATH = os.path.join(BRAIN_PATH, "rooms", "memory", "index_log.json")
SKILLS_DIR = os.path.expanduser("~/.openclaw/skills")


def memory_midnight_report() -> dict:
    from datetime import timezone, timedelta
    cst = timezone(timedelta(hours=-6))
    today_str = datetime.now(cst).strftime("%Y-%m-%d")

    stats = get_vault_stats()
    report_dir = os.path.join(BRAIN_PATH, "rooms", "memory", "reports")

    largest_room = stats["room_sizes"][0]["room"] if stats.get("room_sizes") else None

    data = {
        "run_date":       today_str,
        "briefs_count":   stats["briefs_count"],
        "verdicts_count": stats["verdicts_count"],
        "reports_count":  stats["reports_count"],
        "skills_count":   stats["skills_count"],
        "total_md_files": stats["total_md_files"],
        "total_kb":       stats["total_kb"],
        "largest_room":   largest_room,
    }

    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, "latest_report.json"), "w") as f:
        json.dump(data, f, indent=2)

    return data


def get_vault_stats() -> dict:
    rooms_dir = Path(BRAIN_PATH) / "rooms"
    total_bytes = 0
    room_sizes = {}

    # Count specific artifact types
    briefs_count = 0
    verdicts_count = 0
    reports_count = 0
    skills_count = 0

    try:
        brief_dir = rooms_dir / "research" / "briefs"
        briefs_count = len(list(brief_dir.glob("*.md"))) if brief_dir.exists() else 0
    except Exception:
        pass

    try:
        verdict_dir = rooms_dir / "approval" / "verdicts"
        verdicts_count = len(list(verdict_dir.glob("*.md"))) if verdict_dir.exists() else 0
    except Exception:
        pass

    try:
        for reports_dir in rooms_dir.glob("*/reports"):
            if reports_dir.is_dir():
                reports_count += sum(
                    1 for f in reports_dir.glob("*.json")
                    if f.name != "latest_report.json"
                )
    except Exception:
        pass

    try:
        vault_skills = list((rooms_dir / "armory" / "skills").glob("*.md")) if (rooms_dir / "armory" / "skills").exists() else []
        openclaw_skills = list(Path(SKILLS_DIR).glob("*.md")) if Path(SKILLS_DIR).exists() else []
        skills_count = len(vault_skills) + len(openclaw_skills)
    except Exception:
        pass

    # Per-room file sizes
    try:
        for room_path in sorted(rooms_dir.iterdir()):
            if not room_path.is_dir():
                continue
            room_bytes = sum(f.stat().st_size for f in room_path.rglob("*") if f.is_file())
            room_sizes[room_path.name] = room_bytes
            total_bytes += room_bytes
    except Exception:
        pass

    # Total .md files in vault
    total_md = 0
    try:
        total_md = sum(1 for _ in Path(BRAIN_PATH).rglob("*.md"))
    except Exception:
        pass

    return {
        "briefs_count":   briefs_count,
        "verdicts_count": verdicts_count,
        "reports_count":  reports_count,
        "skills_count":   skills_count,
        "total_md_files": total_md,
        "total_bytes":    total_bytes,
        "total_kb":       round(total_bytes / 1024, 1),
        "room_sizes":     [
            {"room": k, "bytes": v, "kb": round(v / 1024, 1)}
            for k, v in sorted(room_sizes.items(), key=lambda x: -x[1])
        ],
        "checked_at":     datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }


def compress_vault(keep_n: int = 5) -> dict:
    rooms_dir = Path(BRAIN_PATH) / "rooms"
    archived_total = 0
    archived_bytes = 0
    room_results = []

    for reports_dir in sorted(rooms_dir.glob("*/reports")):
        if not reports_dir.is_dir():
            continue
        room_name = reports_dir.parent.name

        # Timestamped files only — skip latest_report.json
        candidates = sorted(
            [f for f in reports_dir.glob("*") if f.is_file() and f.name != "latest_report.json"],
            key=lambda f: f.name,
            reverse=True,
        )
        to_archive = candidates[keep_n:]
        if not to_archive:
            continue

        archive_dir = reports_dir.parent / "archive"
        archive_dir.mkdir(exist_ok=True)

        moved = []
        for f in to_archive:
            dest = archive_dir / f.name
            archived_bytes += f.stat().st_size
            shutil.move(str(f), str(dest))
            moved.append(f.name)
        archived_total += len(moved)
        room_results.append({"room": room_name, "archived": len(moved), "files": moved})

    return {
        "keep_n":         keep_n,
        "rooms_scanned":  len(list(rooms_dir.glob("*/reports"))),
        "files_archived": archived_total,
        "bytes_freed":    archived_bytes,
        "kb_freed":       round(archived_bytes / 1024, 1),
        "rooms":          room_results,
        "completed_at":   datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }


def export_cold_storage() -> dict:
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    zip_path = os.path.join(BACKUPS_DIR, f"vault_{ts}.zip")

    files_zipped = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BRAIN_PATH):
            # Never include customers/ — PII isolation
            dirs[:] = [d for d in dirs if d != "customers"]
            for fname in files:
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, BRAIN_PATH)
                zf.write(fpath, arcname)
                files_zipped += 1

    zip_size = os.path.getsize(zip_path)
    return {
        "zip_path":    zip_path,
        "files_zipped": files_zipped,
        "zip_bytes":   zip_size,
        "zip_kb":      round(zip_size / 1024, 1),
        "zip_mb":      round(zip_size / (1024 * 1024), 3),
        "exported_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }


def run_index() -> dict:
    vault_root = Path(BRAIN_PATH)
    entries = []
    total_chars = 0

    for md_path in sorted(vault_root.rglob("*.md")):
        # Skip PII
        if "customers" in md_path.parts:
            continue
        try:
            text = md_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        char_count = len(text)
        total_chars += char_count

        # Derive room from path relative to rooms/
        try:
            rel = md_path.relative_to(vault_root / "rooms")
            room = rel.parts[0] if rel.parts else "root"
        except ValueError:
            room = "root"

        entries.append({
            "room":      room,
            "filename":  md_path.name,
            "path":      str(md_path.relative_to(vault_root)),
            "char_count": char_count,
            "preview":   text[:100].replace("\n", " ").strip(),
        })

    log = {
        "files_scanned": len(entries),
        "total_chars":   total_chars,
        "total_kb":      round(total_chars / 1024, 1),
        "indexed_at":    datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        "chromadb_ready": False,
        "note":          "ChromaDB stub — logs what would be indexed. Install chromadb and wire collection to activate.",
        "entries":       entries,
    }

    os.makedirs(os.path.dirname(INDEX_LOG_PATH), exist_ok=True)
    with open(INDEX_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)

    # Return summary only (entries list can be large)
    return {
        "files_scanned":  log["files_scanned"],
        "total_chars":    log["total_chars"],
        "total_kb":       log["total_kb"],
        "chromadb_ready": log["chromadb_ready"],
        "note":           log["note"],
        "log_path":       INDEX_LOG_PATH,
        "indexed_at":     log["indexed_at"],
    }
