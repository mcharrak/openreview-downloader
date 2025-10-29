<div align="center">

# 🌟 OpenReview Review Downloader 🌟

![Python Version](https://img.shields.io/badge/python-3.7+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Maintained](https://img.shields.io/badge/status-maintained-brightgreen.svg)

A simple, powerful Python script to download your OpenReview reviews as raw Markdown and text files.

</div>

Tired of copy-pasting reviews for your rebuttal, only to have all the $LaTeX$ equations break? This tool programmatically fetches the **raw, un-rendered review text**, preserving all $MathJax$ and Markdown formatting.

Perfect for sharing with co-authors, feeding into LLMs (like ChatGPT or Gemini) for summarisation, or drafting your rebuttal in a `.tex` file.

---

## Why Use This?

During the high-pressure rebuttal period, manually copying reviews is frustrating.

**The Problem:** When you copy from the OpenReview website, rendered math breaks.
* **You copy:** `The authors' assumption in Eq. 1 (where X ⟂ Y) is flawed.`
* **You wanted:** `The authors' assumption in Eq. 1 (where `$X \perp Y$`) is flawed.`

**The Solution:** This script uses the official OpenReview API to log in and download the original raw text.
* ✅ Saves all reviews to a local `reviews/` folder.
* ✅ Preserves all LaTeX (`$...$` and `$$...$$`).
* ✅ Automatically ignored by Git (via `.gitignore`) to protect your privacy.

---

## 🚀 Installation

1. **Clone the Repository:**
    ```bash
    git clone https://github.com/YOUR_USERNAME/openreview-downloader.git
    cd openreview-downloader
    ```

2. **(Recommended) Create a Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3. **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

---

## 🔬 How to Use

The script offers two ways to run. You will be securely prompted for your OpenReview login password.

### Recommended Method (Paste your URL)

1. **Find Your Paper's URL:**
    * Log in to OpenReview and go to your Author Console for the conference (e.g., "AAAI 2026 Author Console").
    * You will see a table of your submissions with columns like **{Submission Summary, Official Review, Decision}**.
    * Under the **"Submission Summary"** column, **right-click on your paper's title**.
    * Select **"Copy Link Address"** (or similar). This link is ideal as it often contains the `referrer` info, which helps the script auto-detect the `venue_id`.

2. **Run the Script:**
    Paste the copied URL in the `--url` argument. The script is robust and works with all common OpenReview URL formats:
    * **Long URLs (best):** `...&referrer=[Author%20Console](...)`
    * **Short URLs:** `...?id=...`
    * **Fragment URLs:** `...?id=...#discussion`

    ```bash
    python download_reviews.py --email "your_email@domain.com" --url "PASTE_THE_COPIED_URL_HERE"
    ```

    *Example:*
    ```bash
    python download_reviews.py --email "max.mustermann@gmail.com" --url "https://openreview.net/forum?id=sWmLjUXPsq&referrer=%5BAuthor%20Console%5D"
    ```

### Backup Method (Manual IDs)

If the script cannot auto-detect the `venue_id`, it will ask you to provide it manually.

* `forum_id`: The `id` from the URL (e.g., `sWmLjUXPsq`)
* `venue_id`: The conference ID (e.g., `AAAI.org/2026/Conference`)

```bash
python download_reviews.py --email "your_email@domain.com" --forum_id "sWmLjUXPsq" --venue_id "AAAI.org/2026/Conference"
```

---

## ✅ Output

On success, the script will create a folder `reviews/` and save your reviews there.

```
✅ Success! All 5 reviews have been saved.
Markdown file: reviews/reviews_sWmLjUXPsq.md
Text file:     reviews/reviews_sWmLjUXPsq.txt
```

---

## 🤝 Contributing

Found a bug or have an improvement? Feel free to open an issue or submit a pull request!

---

## 📜 License

This project is licensed under the MIT License. See the LICENSE file for details.

---

**Keywords:** OpenReview, Machine Learning, Rebuttal, Download Reviews, LaTeX, MathJax, AI, ML, NeurIPS, ICLR, ICML, AAAI, CVPR, Causal Discovery, Python, Script
