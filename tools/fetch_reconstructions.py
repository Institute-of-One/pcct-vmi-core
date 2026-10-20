"""Parallel segmented downloader for the Walnut Reconstructions.zip (19 GB).

Single-connection throughput to Zenodo from this host is ~1.8 MB/s, which
would put a 19 GB file at ~3 hours. Zenodo supports HTTP range requests
(verified 206), so this script downloads 64 MB segments on 12 threads and
resumes cleanly across invocations:

    python tools/fetch_reconstructions.py            # one ~4.5 min burst
    python tools/fetch_reconstructions.py            # repeat until done
    ...
    # when all segments are complete the parts are concatenated, the md5
    # is verified against the Zenodo record, and the parts are removed.

Each run is time-capped (--max-seconds, default 270) so it fits a single
foreground shell call; re-running continues where it left off. Progress is
persistent: completed segments are exactly-sized part files under
data/walnut/, so interruption never corrupts finished segments.

The file size and checksum are taken from the Zenodo API at run time, never
hard-coded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "data" / "walnut"
RECORD_API = "https://zenodo.org/api/records/17328375"
FILE_KEY = "Reconstructions.zip"


def _api_file_info() -> tuple[int, str]:
    with urllib.request.urlopen(RECORD_API, timeout=60) as resp:
        record = json.load(resp)
    for f in record["files"]:
        if f["key"] == FILE_KEY:
            checksum = f["checksum"]
            algo, _, value = checksum.partition(":")
            if algo != "md5":
                raise SystemExit(f"unexpected checksum scheme: {checksum}")
            return int(f["size"]), value
    raise SystemExit(f"{FILE_KEY} not found in record")


def _fetch_range(url: str, start: int, end: int, path: Path) -> int:
    """Download bytes [start, end] into path (appending); returns bytes written."""
    req = urllib.request.Request(url)
    req.add_header("Range", f"bytes={start}-{end}")
    written = 0
    with urllib.request.urlopen(req, timeout=120) as resp, path.open("ab") as fh:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            written += len(chunk)
    return written


def _download_segment(url: str, seg_start: int, seg_end: int, part: Path) -> str:
    expected = seg_end - seg_start + 1
    while True:
        have = part.stat().st_size if part.exists() else 0
        if have >= expected:
            return "done"
        _fetch_range(url, seg_start + have, seg_end, part)
        time.sleep(0.5)  # gentle pacing between retries within a segment


def _concatenate(parts: list[Path], final: Path, deadline: float) -> int:
    """Append all parts to final, resuming from the current file size.

    Returns the number of bytes present in final when the function returns
    (== total size when complete). Safe across interruptions: the file is
    pure append, and parts are never modified during this phase.
    """
    done = final.stat().st_size if final.exists() else 0
    with final.open("ab") as out:
        for p in parts:
            size = p.stat().st_size
            if done >= size:
                done -= size
                continue
            with p.open("rb") as fh:
                fh.seek(done)
                done = 0
                while True:
                    if time.time() > deadline:
                        return final.stat().st_size
                    chunk = fh.read(1 << 22)
                    if not chunk:
                        break
                    out.write(chunk)
    return final.stat().st_size


def _verify_md5(final: Path, expected: str, deadline: float) -> bool:
    """Whole-file md5.

    A hashlib object is not picklable on this interpreter, so there is no
    resumable state: this pass must finish within the caller's time budget.
    The caller keeps the run budget small enough (and reads are much faster
    than the write phase), so one pass suffices; if it is interrupted the
    whole pass simply re-runs.
    """
    md5 = hashlib.md5()
    with final.open("rb") as fh:
        while True:
            chunk = fh.read(1 << 22)
            if not chunk:
                break
            md5.update(chunk)
            if time.time() > deadline:
                return False
    digest = md5.hexdigest()
    if digest != expected:
        raise SystemExit(
            f"md5 mismatch: got {digest}, expected {expected}; "
            "downloaded file kept for inspection, parts kept"
        )
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--segment-mb", type=int, default=64)
    ap.add_argument("--max-seconds", type=float, default=270.0)
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    total, md5_expected = _api_file_info()
    seg = args.segment_mb * (1 << 20)
    url = f"https://zenodo.org/records/17328375/files/{FILE_KEY}?download=1"
    parts = [DEST / f"{FILE_KEY}.part{i:04d}" for i in range((total + seg - 1) // seg)]
    final = DEST / FILE_KEY

    def seg_range(i: int) -> tuple[int, int]:
        return i * seg, min((i + 1) * seg, total) - 1

    t0 = time.time()
    pending = [
        i
        for i, p in enumerate(parts)
        if not p.exists() or p.stat().st_size < seg_range(i)[1] - seg_range(i)[0] + 1
    ]
    done_before = len(parts) - len(pending)
    print(
        f"total {total / 1e9:.2f} GB, {len(parts)} segments, "
        f"{done_before} already done, {len(pending)} pending"
    )

    def work(i: int) -> None:
        s, e = seg_range(i)
        _download_segment(url, s, e, parts[i])

    timed_out = False
    pool = ThreadPoolExecutor(max_workers=args.workers)
    futures = [pool.submit(work, i) for i in pending]
    try:
        for f in futures:
            remaining = args.max_seconds - (time.time() - t0)
            if remaining <= 0:
                timed_out = True
                break
            f.result(timeout=remaining)
    except (TimeoutError, KeyboardInterrupt):
        timed_out = True
    finally:
        # Do NOT wait for in-flight downloads: a worker blocked in a slow
        # read would keep the process alive past the caller's time budget.
        # os._exit skips non-daemon thread joining; part files on disk are
        # the resume state, so abandoning threads mid-write is safe — a
        # part is only ever appended, and the next run re-checks sizes.
        if timed_out:
            import os

            print("run time cap reached; abandoning in-flight threads.", flush=True)
            os._exit(0)
        pool.shutdown(wait=True)

    complete = all(
        p.exists() and p.stat().st_size == seg_range(i)[1] - seg_range(i)[0] + 1
        for i, p in enumerate(parts)
    )
    if not complete:
        finished = (
            sum(
                1
                for i, p in enumerate(parts)
                if p.stat().st_size == seg_range(i)[1] - seg_range(i)[0] + 1
            )
            if all(p.exists() for p in parts)
            else -1
        )
        print(
            f"run time cap reached; not all segments complete "
            f"({finished}/{len(parts)}). Re-run to continue."
        )
        return

    # --- concatenation (resumable: final grows byte-exactly across runs) ---
    print("all segments complete; concatenating ...")
    concat_done = _concatenate(parts, final, t0 + args.max_seconds * 0.6)
    if concat_done < total:
        print(
            f"concatenation paused at {concat_done}/{total} bytes "
            f"(run time cap). Re-run to continue."
        )
        return

    # --- md5 verification (single pass; must fit the remaining budget) ---
    verified = _verify_md5(final, md5_expected, t0 + args.max_seconds * 0.95)
    if not verified:
        print("md5 verification paused (run time cap). Re-run to continue.")
        return
    for p in parts:
        p.unlink()
    print(f"verified md5 {md5_expected}; wrote {final} ({final.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
