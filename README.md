<div align="center">

# 🌟 OpenReview Review Downloader 🌟

![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Maintained](https://img.shields.io/badge/status-maintained-brightgreen.svg)

A simple, powerful Python script to download your OpenReview reviews as raw Markdown, text, and JSON files.

</div>

Tired of copy-pasting reviews for your rebuttal, only to have all the $LaTeX$ equations break? This tool programmatically fetches the **raw, un-rendered review text**, preserving $MathJax$ and Markdown formatting.

Perfect for sharing with co-authors, feeding into LLMs (like ChatGPT or Gemini) for summarisation, analysing scores/confidence in Python, or drafting your rebuttal in a `.tex` file.

---

## Why Use This?

During the high-pressure rebuttal period, manually copying reviews is frustrating.

**The Problem:** When you copy from the OpenReview website, rendered math breaks.

* **You copy:** `The authors' assumption in Eq. 1 (where X ⟂ Y) is flawed.`

* **You wanted:** `The authors' assumption in Eq. 1 (where $X \perp Y$) is flawed.`

**The Solution:** This script uses the official OpenReview API to log in and download the original raw text.

* ✅ Preserves raw LaTeX / MathJax (`$...$` and `$$...$$`)
* ✅ Saves exports to a local `reviews/` folder
* ✅ Supports **Markdown**, **text**, and **JSON** output
* ✅ Exports **every readable reply by default** — reviews, replies, meta-reviews, decisions, comments, and other forum notes
* ✅ Works across many venues via **heuristic classification** (review / meta-review / decision / comment / response)
* ✅ Tries **API v2 first**, then falls back to **API v1**
* ✅ Supports filtering to **direct replies only** (`--direct-only`) for cleaner rebuttal exports
* ✅ Keeps your exports local (and can be ignored via `.gitignore`) for privacy

---

## 🚀 Installation

1. **Clone the Repository:**

    ```bash
    git clone https://github.com/YOUR_USERNAME/openreview-downloader.git
    cd openreview-downloader
    ```

2. **(Recommended) Create a Virtual Environment:**

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3. **Install Dependencies:**

    If you use a `requirements.txt` file:

    ```bash
    pip install -r requirements.txt
    ```

    Or install directly:

    ```bash
    pip install openreview-py
    ```

---

## 🔬 How to Use

The script offers multiple ways to run. You will be securely prompted for your OpenReview login password (unless you pass it via environment variable).

### Recommended Method (Paste your URL)

1. **Find Your Paper's URL:**
    * Log in to OpenReview and go to your Author Console for the conference (for example, "AAAI 2026 Author Console").
    * You will see a table of your submissions with columns like **Submission Summary**, **Official Review**, **Decision**, etc.
    * Under the **Submission Summary** column, **right-click your paper title**.
    * Select **Copy Link Address** (or similar).

    This link is ideal because it often contains a `referrer` field, which may help the script auto-detect the `venue_id`.

2. **Run the Script:**

    The parser is robust and supports common OpenReview URL variants:
    * **Long URLs (best):** `...&referrer=[Author%20Console](...)`
    * **Short URLs:** `...?id=...`
    * **Fragment URLs:** `...?id=...#discussion`
    * Pasted markdown-style links: `[paper](https://openreview.net/forum?id=...)`

    ```bash
    python download_reviews.py --email "your_email@domain.com" --url "PASTE_THE_COPIED_URL_HERE"
    ```

    *Example:*

    ```bash
    python download_reviews.py --email "max.mustermann@gmail.com" --url "https://openreview.net/forum?id=sWmLjUXPsq&referrer=%5BAuthor%20Console%5D"
    ```

    By default the export includes **all readable notes in the forum thread**,
    not only reviewer reports. This is important because NeurIPS, ICML, ICLR,
    AISTATS, AAAI, UAI, and other venues can publish a meta-review, decision,
    or author/reviewer discussion as separate notes. Nested replies are also
    included unless you explicitly choose `--direct-only`.

    To intentionally make a reviewer-reports-only export, opt in to that
    narrower filter:

    ```bash
    python download_reviews.py --email "your_email@domain.com" --url "PASTE_THE_COPIED_URL_HERE" --include review
    ```

    For a lossless, machine-readable companion to the Markdown and text
    exports, include JSON as well:

    ```bash
    python download_reviews.py --email "your_email@domain.com" --url "PASTE_THE_COPIED_URL_HERE" --formats md,txt,json
    ```

---

### Backup Method (Manual IDs)

If you already know the IDs, you can pass them directly.

* `forum_id`: The paper forum ID (for example, `sWmLjUXPsq`)
* `venue_id`: Optional conference ID (for example, `AAAI.org/2026/Conference`)  
  (`venue_id` is only used as a fallback in some retrieval paths)

```bash
python download_reviews.py --email "your_email@domain.com" --forum_id "sWmLjUXPsq" --venue_id "AAAI.org/2026/Conference"
