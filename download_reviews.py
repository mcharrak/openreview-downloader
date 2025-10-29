import openreview
import getpass
import sys
import argparse
from urllib.parse import urlparse, parse_qs
import os  # <-- ADDED THIS IMPORT

def parse_url(url):
    """
    Parses the OpenReview URL to extract forum_id and potentially venue_id.
    """
    try:
        # Robustness Fix: Remove any URL fragment (e.g., #discussion)
        if '#' in url:
            url = url.split('#', 1)[0]
            
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        
        if 'id' not in query_params:
            print(f"Error: Could not find 'id' in the URL query: {url}")
            return None, None
            
        forum_id = query_params['id'][0]
        venue_id = None

        if 'referrer' in query_params:
            referrer = query_params['referrer'][0]
            if 'id=' in referrer:
                parts = referrer.split('id=')[-1].split('/')
                if len(parts) >= 3:
                    venue_id = f"{parts[0]}/{parts[1]}/{parts[2]}"
                    print(f"Intelligently parsed venue_id: {venue_id}")

        return forum_id, venue_id

    except Exception as e:
        print(f"Error parsing URL: {e}")
        return None, None

def fetch_reviews(client, forum_id, venue_id):
    """
    Fetches the review notes, trying multiple common invitation IDs before
    falling back to a broad search.
    """
    
    reviews = []
    
    if venue_id:
        common_invitations = [
            f'{venue_id}/-/Official_Review', # Most common default
            f'{venue_id}/-/Review'           # Second most common
        ]
        
        for i, invitation in enumerate(common_invitations):
            attempt_num = i + 1
            print(f"\nAttempt {attempt_num}: Searching for reviews with invitation: '{invitation}'...")
            try:
                reviews = client.get_all_notes(
                    invitation=invitation,
                    forum=forum_id
                )
                if reviews:
                    print(f"Success: Found {len(reviews)} review(s) with this invitation.")
                    return reviews
                else:
                    print(f"Attempt {attempt_num} found 0 reviews.")
            except Exception as e:
                print(f"Attempt {attempt_num} failed with error: {e}")
        
        print("\nAll default invitation searches failed.")

    else:
        print("\nVenue ID is unknown. Skipping default invitation search.")

    print("Proceeding to (Fallback) broad search for all replies in this forum...")
    
    try:
        all_replies = client.get_all_notes(forum=forum_id)
        reviews = [
            r for r in all_replies 
            if r.id != forum_id and ('review' in r.content or 'comment' in r.content)
        ]
        
        if reviews:
            try:
                actual_invitation = reviews[0].invitation
                print(f"\nBroad search found {len(reviews)} reviews.")
                print(f"✨ Info: These reviews appear to use the invitation: '{actual_invitation}'")
            except Exception:
                pass 
            
            return reviews

    except Exception as e:
        print(f"Broad search failed: {e}")
        return []

    return []

def main():
    parser = argparse.ArgumentParser(
        description="Download OpenReview reviews as raw text and Markdown.",
        epilog="Example (URL): python download_reviews.py --email u@x.com --url 'https://openreview.net/forum?id=...'\n" \
               "Example (Manual): python download_reviews.py --email u@x.com --forum_id '...-f_id' --venue_id 'Conf.org/Year/Venue'"
    )
    parser.add_argument('--email', type=str, required=True, help="Your OpenReview login email.")
    parser.add_argument('--url', type=str, help="The full OpenReview URL of your paper. (e.g., 'https://openreview.net/forum?id=...')")
    
    parser.add_argument('--forum_id', type=str, help="Manual override for paper's forum ID (the 'id' in the URL).")
    parser.add_argument('--venue_id', type=str, help="Manual override for the venue ID (e.g., 'AAAI.org/2026/Conference').")

    args = parser.parse_args()

    forum_id = args.forum_id
    venue_id = args.venue_id

    if args.url:
        print(f"Parsing URL: {args.url}")
        parsed_forum_id, parsed_venue_id = parse_url(args.url)
        if not forum_id:
            forum_id = parsed_forum_id
        if not venue_id and parsed_venue_id:
            venue_id = parsed_venue_id
    
    if not forum_id:
        print("\nError: Could not determine Paper Forum ID. Please provide it via --url or --forum_id.")
        sys.exit(1)

    try:
        password = getpass.getpass(prompt=f"Enter OpenReview password for {args.email}: ")
        client = openreview.api.OpenReviewClient(
            baseurl='https://api2.openreview.net',
            username=args.email,
            password=password
        )
        print(f"\nSuccessfully logged in as {args.email} (using v2 API).")
    
    except Exception as e:
        print(f"\nLogin failed: {e}")
        if '401' in str(e):
             print("This is an 'Unauthorized' error. Please double-check your credentials.")
        sys.exit(1)

    if not venue_id:
        print("\nVenue ID not provided or parsed. Trying to auto-detect from submission note...")
        try:
            submission_note = client.get_note(id=forum_id)
            if hasattr(submission_note, 'invitation'):
                venue_id = submission_note.invitation.split('/-/')[0]
                print(f"Auto-detected Venue ID: {venue_id}")
            else:
                raise Exception("Submission note found, but it has no 'invitation' attribute.")
        except Exception as e:
            print(f"Warning: Could not auto-detect Venue ID: {e}")
            print("Will proceed with broad search fallback.")

    reviews = fetch_reviews(client, forum_id, venue_id)

    if not reviews:
        print("\nNo reviews were found. They may not be available or visible to you yet.")
        sys.exit(0)

    # --- 5. Write to Files ---
    
    # --- NEW: Create a directory for reviews ---
    OUTPUT_DIR = "reviews"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # --- NEW: Update output paths to use the new directory ---
    output_filename_md = os.path.join(OUTPUT_DIR, f"reviews_{forum_id}.md")
    output_filename_txt = os.path.join(OUTPUT_DIR, f"reviews_{forum_id}.txt")
    
    print(f"\n--- Found {len(reviews)} review(s). Now writing to {output_filename_md} and {output_filename_txt}... --- \n")

    try:
        with open(output_filename_md, 'w', encoding='utf-8') as f_md, \
             open(output_filename_txt, 'w', encoding='utf-8') as f_txt:
            
            for i, rev in enumerate(reviews):
                print(f"Processing Review (ID: {rev.id})...")

                f_md.write(f"## Review (ID: {rev.id})\n\n")
                f_txt.write(f"--- Review (ID: {rev.id}) ---\n\n")

                raw_text = None
                if 'review' in rev.content and 'value' in rev.content['review']:
                    raw_text = rev.content['review']['value']
                elif 'comment' in rev.content and 'value' in rev.content['comment']:
                    raw_text = rev.content['comment']['value']
                
                if raw_text:
                    f_md.write(raw_text)
                    f_txt.write(raw_text)
                else:
                    f_md.write("*Could not find 'review' or 'comment' text.*\n")
                    f_txt.write("Could not find 'review' or 'comment' text.\n")
                    print(f"Warning: Could not find text for Review (ID: {rev.id}).")
                
                f_md.write("\n\n---\n\n")
                f_txt.write("\n\n" + "="*80 + "\n\n")

        print(f"\n✅ Success! All {len(reviews)} reviews have been saved.")
        print(f"Markdown file: {output_filename_md}")
        print(f"Text file:     {output_filename_txt}")

    except Exception as e:
        print(f"Error writing to file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
    