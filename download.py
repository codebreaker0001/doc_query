"""
Download a chosen set of arXiv papers as PDFs into ./data.

    python download_arxiv_pdfs.py

Stdlib only — no pip install needed. Edit PAPERS to pick your set: keys are
arXiv IDs, values are the filename stem to save as (readable names help later).

Good arXiv citizenship: this uses a descriptive User-Agent and sleeps between
downloads so you don't get rate-limited (arXiv asks bulk fetchers to go slow).
"""

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

OUT_DIR = Path("data")
DELAY_SECONDS = 3          # pause between downloads (be polite to arXiv)
MAX_RETRIES = 3
USER_AGENT = "doc-query-eval-downloader/1.0 (retriever evaluation; contact: you@example.com)"

# arxiv_id -> filename stem (without .pdf). Edit freely.
PAPERS = {
    "1706.03762": "attention_is_all_you_need",
    "1810.04805": "bert",
    "2005.14165": "gpt3_few_shot_learners",
    "1512.03385": "resnet_deep_residual_learning",
    "1406.2661":  "generative_adversarial_nets",
    "1412.6980":  "adam_optimizer",
    "2005.11401": "retrieval_augmented_generation",
    "2106.09685": "lora",
    "2010.11929": "vision_transformer",
    "2006.11239": "ddpm_diffusion",
    "2103.00020": "clip",
    "2201.11903": "chain_of_thought",
    "2203.02155": "instructgpt",
    "2307.09288": "llama2",
}


def download_one(arxiv_id: str, stem: str) -> str:
    """Returns one of: 'ok', 'skip', 'fail'."""
    dest = OUT_DIR / f"{stem}.pdf"
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  skip  {dest.name} (already downloaded)")
        return "skip"

    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            # arXiv sometimes returns an HTML holding page when throttled or
            # when an ID is wrong — verify we actually got a PDF.
            if not data.startswith(b"%PDF"):
                print(f"  FAIL  {arxiv_id}: response wasn't a PDF (check the ID / rate limit)")
                return "fail"
            dest.write_bytes(data)
            print(f"  ok    {dest.name}  ({len(data) // 1024} KB)")
            return "ok"
        except urllib.error.HTTPError as e:
            if e.code == 429:  # too many requests — back off harder
                wait = DELAY_SECONDS * 2 * attempt
                print(f"  ...   {arxiv_id}: rate limited, waiting {wait}s (attempt {attempt})")
                time.sleep(wait)
            elif e.code == 404:
                print(f"  FAIL  {arxiv_id}: 404 — no such paper/version")
                return "fail"
            else:
                print(f"  ...   {arxiv_id}: HTTP {e.code} (attempt {attempt})")
                time.sleep(DELAY_SECONDS * attempt)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  ...   {arxiv_id}: {e} (attempt {attempt})")
            time.sleep(DELAY_SECONDS * attempt)

    print(f"  FAIL  {arxiv_id}: gave up after {MAX_RETRIES} attempts")
    return "fail"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {len(PAPERS)} papers into {OUT_DIR.resolve()}\n")

    counts = {"ok": 0, "skip": 0, "fail": 0}
    for i, (arxiv_id, stem) in enumerate(PAPERS.items()):
        counts[download_one(arxiv_id, stem)] += 1
        if i < len(PAPERS) - 1:
            time.sleep(DELAY_SECONDS)

    print(f"\nDone: {counts['ok']} downloaded, {counts['skip']} skipped, {counts['fail']} failed.")
    if counts["fail"]:
        print("For any failure, search the paper title on arxiv.org and grab the PDF manually.")
        sys.exit(1)


if __name__ == "__main__":
    main()