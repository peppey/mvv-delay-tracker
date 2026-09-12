from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from google.cloud import storage


BUCKET_NAME = os.environ.get("MVV_DATA_BUCKET", "mvv-delay-tracker-data")
GITHUB_REPOSITORY = os.environ.get(
    "GITHUB_REPOSITORY", "peppey/mvv-delay-tracker"
)
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

REALTIME_FILES = [
    "data/realtime/mvv_realtime.parquet",
    "docs/munich_delay_statistics.png",
    "docs/munich_delays.png",
    "docs/delay_comparison.png",
    "docs/line_comparison.png",
    "docs/delay_heatmap.png",
    "README.md",
]
STATIC_FILES = [
    "data/static/.gtfs_metadata.json",
    "data/static/agency.txt",
    "data/static/routes.txt",
    "data/static/trips.txt",
    "data/static/munich_stops.csv",
    "data/static/stop_times.txt",
    "data/static/calendar.txt",
    "data/static/calendar_dates.txt",
    "data/quality/realtime_departure_failures.csv",
    "data/quality/munich_trip_completeness.csv",
    "data/quality/munich_trip_completeness_by_line.csv",
    "docs/munich_trip_completeness.png",
    "docs/munich_trip_completeness_by_line.png",
]


def sync_from_bucket(paths: list[str], bucket: storage.Bucket) -> None:
    for relative_path in paths:
        destination = Path(relative_path)
        blob = bucket.blob(relative_path)
        if blob.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(destination)


def sync_to_bucket(paths: list[str], bucket: storage.Bucket) -> None:
    for relative_path in paths:
        source = Path(relative_path)
        if source.exists():
            bucket.blob(relative_path).upload_from_filename(source)


def update_readme_access_date() -> None:
    readme_path = Path("README.md")
    readme = readme_path.read_text()
    current_date = datetime.now().strftime("%B %Y")
    updated_readme = re.sub(
        r"^\*\*Last accessed:\*\* .*$",
        f"**Last accessed:** {current_date}",
        readme,
        flags=re.MULTILINE,
    )
    readme_path.write_text(updated_readme)


def run_command(*command: str) -> None:
    subprocess.run(command, check=True)


def push_to_github(paths: list[str], message: str) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        checkout = Path(temporary_directory) / "repository"
        git_url = (
            f"https://x-access-token:{quote(GITHUB_TOKEN, safe='')}"
            f"@github.com/{GITHUB_REPOSITORY}.git"
        )
        git_environment = os.environ | {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "cloud-run[bot]",
            "GIT_AUTHOR_EMAIL": "cloud-run[bot]@users.noreply.github.com",
            "GIT_COMMITTER_NAME": "cloud-run[bot]",
            "GIT_COMMITTER_EMAIL": "cloud-run[bot]@users.noreply.github.com",
        }
        subprocess.run(
            ["git", "clone", "--branch", GITHUB_BRANCH, git_url, checkout],
            check=True,
            env=git_environment,
        )
        for relative_path in paths:
            source = Path(relative_path)
            destination = checkout / relative_path
            if source.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        run_command("git", "-C", str(checkout), "config", "user.name", "cloud-run[bot]")
        run_command(
            "git", "-C", str(checkout), "config", "user.email",
            "cloud-run[bot]@users.noreply.github.com",
        )
        run_command("git", "-C", str(checkout), "add", "--", *paths)
        changes = subprocess.run(
            ["git", "-C", str(checkout), "diff", "--cached", "--quiet"],
            check=False,
        )
        if changes.returncode == 0:
            print("No GitHub changes to push.")
            return
        run_command("git", "-C", str(checkout), "commit", "-m", message)
        run_command("git", "-C", str(checkout), "push", "origin", GITHUB_BRANCH)


def main() -> None:
    job_name = os.environ.get("MVV_JOB_TYPE", "realtime")
    if job_name not in {"realtime", "static"}:
        raise ValueError("CLOUD_RUN_JOB must be 'realtime' or 'static'")

    paths = REALTIME_FILES if job_name == "realtime" else STATIC_FILES
    bucket = storage.Client().bucket(BUCKET_NAME)
    sync_from_bucket(paths, bucket)

    if job_name == "realtime":
        run_command("python", "scripts/update_parquet.py")
        update_readme_access_date()
        message = "Update MVV data and plot"
    else:
        run_command("python", "scripts/update_static_data.py")
        run_command("python", "scripts/check_realtime_data_quality.py")
        message = "Update static GTFS data"

    sync_to_bucket(paths, bucket)
    push_to_github(paths, message)


if __name__ == "__main__":
    main()