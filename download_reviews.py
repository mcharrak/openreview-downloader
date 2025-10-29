import openreview
import getpass
import sys
import argparse
from urllib.parse import urlparse, parse_qs

def parse_url(url):
    """
    Parses the OpenReview URL to extract forum_id and potentially venue_id.
    """
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        
        if 'id' not in query_params:
            print(f"Error: Could not find 'id' in the URL query: {url}")
            return None, None
            
        forum_id = query_params['id'][0]
        venue_id = None

        # Try to intelligently guess venue_id from the referrer
        if 'referrer' in query_params:
            referrer = query_params['referrer'][0]
            # Example referrer: [Author Console](/group?id=AAAI.org/2026/Conference/Authors...
            # We are looking for the "AAAI.org/2026/Conference" part
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
    Fetches the review notes given a forum_id and venue_id.
    """
    review_invitation_id = f'{venue_id}/-/Official_Review'
    print(f"\nUsing Venue ID: {venue_id}")
    print(f"Searching for reviews with invitation: {review_invitation_id}")

    try:
        reviews = client.get_all_notes(
            invitation=review_invitation_id,
            forum=forum_id
        )
    except Exception as e:
        print(f"Error fetching notes with invitation '{review_invitation_id}': {e}")
        print("This might be a permission issue or an incorrect venue_id.")
        return []

    if not reviews:
        print(f"\nFound 0 reviews matching '{review_invitation_id}'.")
        print("This could mean reviews aren't posted, OR the invitation name is different.")
        print("\nTrying a broader search for all replies in this forum...")
        
        try:
            all_replies = client.get_all_notes(forum=forum_id)
            # Filter out the original submission (which has id==forum_id)
            reviews = [
                r for r in all_replies 
                if r.id != forum_id and ('review' in r.content or 'comment' in r.content)
            ]
        except Exception as e:
            print(f"Error during broad search: {e}")
            return []

    return reviews

def main():
    parser = argparse.ArgumentParser(
        description="Download OpenReview reviews as raw text and Markdown.",
        epilog="Example (URL): python download_reviews.py --email u@x.com --url 'https://openreview.net/forum?id=...'\n" \
               "Example (Manual): python download_reviews.py --email u@x.com --forum_id '...-f_id' --venue_id 'Conf.org/Year/Venue'"
    )
    parser.add_argument('--email', type=str, required=True, help="Your OpenReview login email.")
    parser.add_argument('--url', type=str, help="The full OpenReview URL of your paper. (e.g., 'https://openreview.net/forum?id=...')")
    
    # Backup arguments
    parser.add_argument('--forum_id', type=str, help="Manual override for paper's forum ID (the 'id' in the URL).")
    parser.add_argument('--venue_id', type=str, help="Manual override for the venue ID (e.g., 'AAAI.org/2026/Conference').")

    args = parser.parse_args()

    # --- 1. Determine IDs ---
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

    # --- 2. Get Credentials ---
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

    # --- 3. Get Venue ID if missing ---
    if not venue_id:
        print("Venue ID not provided or parsed. Trying to auto-detect from submission note...")
        try:
            submission_note = client.get_note(id=forum_id)
            venue_id = submission_note.invitation.split('/-/')[0]
            print(f"Auto-detected Venue ID: {venue_id}")
        except Exception as e:
            print(f"\nError: Could not auto-detect Venue ID: {e}")
            print("This is a common issue. Please run the script again and provide the Venue ID manually.")
            print("Example: --venue_id 'AAAI.org/2026/Conference'")
            sys.exit(1)

    # --- 4. Fetch Reviews ---
    reviews = fetch_reviews(client, forum_id, venue_id)

    if not reviews:
        print("\nBroad search also found 0 reviews. The reviews may not be available or visible to you yet.")
        sys.exit(0)

    # --- 5. Write to Files ---
    output_filename_md = f"reviews_{forum_id}.md"
    output_filename_txt = f"reviews_{forum_id}.txt"
    
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