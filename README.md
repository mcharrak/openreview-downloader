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

It saves the reviews in two clean files, ready for any use:
* `reviews_[PAPER_ID].md` (A formatted Markdown file)
* `reviews_[PAPER_ID].txt` (A plain text file)

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

The script offers two ways to run. You will be securely prompted for your OpenReview password.

### Recommended Method (Just paste your URL)

The script will automatically parse the `forum_id` (and `venue_id` if possible) from the link.

1.  Find the URL of your paper's OpenReview page.
2.  Run the script with the `--url` and `--email` flags:

    ```bash
    python download_reviews.py --email "your_email@domain.com" --url "[https://openreview.net/forum?id=NDRzOSnDOq&referrer=...AAAI.org/2026/Conference](https://openreview.net/forum?id=NDRzOSnDOq&referrer=...AAAI.org/2026/Conference)..."
    ```

### Backup Method (Manual IDs)

If the URL parsing fails (especially for the `venue_id`), you can provide the IDs manually.

* `forum_id`: The `id` from the URL (e.g., `NDRzOSnDOq`)
* `venue_id`: The conference ID (e.g., `AAAI.org/2026/Conference`)

```bash
python download_reviews.py --email "your_email@domain.com" --forum_id "NDRzOSnDOq" --venue_id "AAAI.org/2026/Conference"
```

### Success!

The script will log in, fetch the reviews, and you will see:

```
✅ Success! All 5 reviews have been saved.
Markdown file: reviews_NDRzOSnDOq.md
Text file:     reviews_NDRzOSnDOq.txt
```

---

## Contributing

Found a bug or have an improvement? Feel free to open an issue or submit a pull request!

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.