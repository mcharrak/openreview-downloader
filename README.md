# 🌟 OpenReview Review Downloader 🌟

A simple, powerful Python script to download your OpenReview reviews as raw Markdown and text files.

Tired of copy-pasting reviews for your rebuttal, only to have all the $LaTeX$ equations break? This tool programmatically fetches the raw, un-rendered review text, preserving all $MathJax$ and Markdown formatting.

Perfect for sharing with co-authors, pasting into LLMs (like ChatGPT or Gemini) for help, or drafting your rebuttal in a `.tex` file.

**Keywords:** OpenReview, Machine Learning, Rebuttal, Download Reviews, LaTeX, MathJax, AI, ML, NeurIPS, ICLR, ICML, AAAI, CVPR, Causal Discovery, Python, Script

---

## The Problem

When you copy-paste a review from the OpenReview website, the rendered mathematical symbols don't copy over correctly.

**You copy this:**
> The authors' assumption in Eq. 1 (where X ⟂ Y) is flawed.

**But you *wanted* this:**
> The authors' assumption in Eq. 1 (where `$X \perp Y$`) is flawed.

This is a major frustration during the high-pressure rebuttal period.

## The Solution

This script uses the official OpenReview API to log in as you and download the **original raw text** of your reviews, perfectly preserving all LaTeX and Markdown.

It saves the reviews in two clean files inside a new `reviews/` folder. This folder is automatically created and ignored by Git (via `.gitignore`) to protect your privacy and prevent you from accidentally committing your private reviews.

Your files will be saved as:
* `reviews/reviews_[PAPER_ID].md` (A formatted Markdown file)
* `reviews/reviews_[PAPER_ID].txt` (A plain text file)

---

## Installation

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/YOUR_USERNAME/openreview-downloader.git](https://github.com/YOUR_USERNAME/openreview-downloader.git)
    cd openreview-downloader
    ```

2.  **(Optional, but recommended) Create a Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

---

## How to Use

The script offers two ways to run. You will be securely prompted for your OpenReview login password.

### Recommended Method (Paste your URL)

1.  **Find Your Paper's URL:**
    * Log in to OpenReview and go to your Author Console for the conference (e.g., "AAAI 2026 Author Console").
    * You will see a table of your submissions with columns like **{Submission Summary, Official Review, Decision}**.
    * Under the **"Submission Summary"** column, **right-click on your paper's title**.
    * Select **"Copy Link Address"** (or similar) from the context menu. This is the best link to use, as it contains all the info the script needs.

2.  **Run the Script:**
    Paste the copied URL in the `--url` argument. The script is robust and works with all OpenReview URL formats:
    * **Long URLs (best):** `...&referrer=[Author%20Console](...)`
    * **Short URLs:** `...?id=...`
    * **Fragment URLs:** `...?id=...#discussion`

    ```bash
    python download_reviews.py --email "your_email@domain.com" --url "PASTE_THE_COPIED_URL_HERE"
    ```
    *Example:*
    ```bash
    python download_reviews.py --email "amine.mcharrak@cs.ox.ac.uk" --url "[https://openreview.net/forum?id=sIpIjUCPso&referrer=%5BAuthor%20Console%5D](https://openreview.net/forum?id=sIpIjUCPso&referrer=%5BAuthor%20Console%5D)(...)"
    ```

### Backup Method (Manual IDs)

If URL parsing fails (e.g., you don't have the `referrer` link), the script will ask you to provide the `venue_id` manually.

* `forum_id`: The `id` from the URL (e.g., `sIpIjUCPso`)
* `venue_id`: The conference ID (e.g., `AAAI.org/2026/Conference`)

```bash
python download_reviews.py --email "your_email@domain.com" --forum_id "sIpIjUCPso" --venue_id "AAAI.org/2026/Conference"