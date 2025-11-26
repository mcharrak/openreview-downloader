import openreview
import getpass
import sys
import argparse
from urllib.parse import urlparse, parse_qs
import os

def parse_url(url):
    """
    Parses the OpenReview URL to extract forum_id and potentially venue_id.
    """
    try:
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
    Fetches the review notes.
    """
    reviews = []
    
    if venue_id:
        common_invitations = [
            f'{venue_id}/-/Official_Review',
            f'{venue_id}/-/Review'
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
            if r.id != forum_id
        ]
        
        if reviews:
            print(f"\nBroad search found {len(reviews)} total replies. Sifting for reviews...")
            return reviews
        else:
            print("\nBroad search found 0 replies to this forum.")
            return []

    except Exception as e:
        print(f"Broad search failed: {e}")
        return []

    return []

def extract_text_from_value(content_item):
    """
    Extracts text from various OpenReview value formats.
    e.g., "string", {"value": "string"}, {"value": 8}, {"value": ["list"]}
    """
    extracted_text = None
    
    if isinstance(content_item, dict) and 'value' in content_item:
        value = content_item['value']
        if isinstance(value, str):
            extracted_text = value
        elif isinstance(value, (int, float)):
            extracted_text = str(value)
        elif isinstance(value, list):
            extracted_text = ", ".join(str(v) for v in value)
    
    elif isinstance(content_item, str):
        extracted_text = content_item
        
    if extracted_text and extracted_text.strip():
        return extracted_text
    return None

def main():
    parser = argparse.ArgumentParser(
        description="Download OpenReview reviews as raw text and Markdown."
    )
    parser.add_argument('--email', type=str, required=True, help="Your OpenReview login email.")
    parser.add_argument('--url', type=str, help="The full OpenReview URL of your paper.")
    parser.add_argument('--forum_id', type=str, help="Manual override for paper's forum ID.")
    parser.add_argument('--venue_id', type=str, help="Manual override for the venue ID.")

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
        print("\nError: Could not determine Paper Forum ID.")
        sys.exit(1)

    try:
        email_to_use = args.email.strip().strip("“”'\"")
        password = getpass.getpass(prompt=f"Enter OpenReview password for {email_to_use}: ")
        client = openreview.api.OpenReviewClient(
            baseurl='https://api2.openreview.net',
            username=email_to_use,
            password=password
        )
        print(f"\nSuccessfully logged in as {email_to_use} (using v2 API).")
    except Exception as e:
        print(f"\nLogin failed: {e}")
        sys.exit(1)

    if not venue_id:
        print("\nVenue ID not provided or parsed. Trying to auto-detect...")
        try:
            submission_note = client.get_note(id=forum_id)
            if hasattr(submission_note, 'invitation'):
                venue_id = submission_note.invitation.split('/-/')[0]
                print(f"Auto-detected Venue ID: {venue_id}")
            else:
                print("Submission note has no 'invitation' attribute.")
        except Exception as e:
            print(f"Warning: Could not auto-detect Venue ID: {e}")

    replies = fetch_reviews(client, forum_id, venue_id)

    if not replies:
        print("\nNo replies were found.")
        sys.exit(0)

    OUTPUT_DIR = "reviews"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    output_filename_md = os.path.join(OUTPUT_DIR, f"reviews_{forum_id}.md")
    output_filename_txt = os.path.join(OUTPUT_DIR, f"reviews_{forum_id}.txt")
    
    print(f"\n--- Sifting {len(replies)} replies... --- \n")
    
    found_review_count = 0
    
    try:
        with open(output_filename_md, 'w', encoding='utf-8') as f_md, \
             open(output_filename_txt, 'w', encoding='utf-8') as f_txt:
            
            for i, note in enumerate(replies):
                
                raw_text_parts = []
                
                # --- DYNAMIC AUTOMATION LOGIC ---
                # Instead of looking for specific keys, we iterate through EVERYTHING in the content.
                # OpenReview API usually returns content in the order it was defined in the form.
                
                if note.content:
                    for key, content_item in note.content.items():
                        
                        # Extract the text regardless of the key name
                        extracted_text = extract_text_from_value(content_item)
                        
                        if extracted_text:
                            # Clean up the key for the header (e.g. "soundness_justification" -> "Soundness Justification")
                            # Handle keys that might already have spaces
                            title = key.replace('_', ' ').title()
                            
                            # Special handling for "Review" or "Comment" keys
                            # If the key is literally "Review", we usually don't need a "### Review" header
                            # as it's redundant with the "Review X" top header.
                            if title.lower() in ['review', 'comment']:
                                raw_text_parts.append(extracted_text)
                            else:
                                raw_text_parts.append(f"### {title}\n\n{extracted_text}")
                
                
                if raw_text_parts:
                    found_review_count += 1
                    print(f"Processing Review {found_review_count} (ID: {note.id})...")
                    
                    final_raw_text = "\n\n".join(raw_text_parts)

                    f_md.write(f"## Review {found_review_count} (ID: {note.id})\n\n")
                    f_txt.write(f"--- Review {found_review_count} (ID: {note.id}) ---\n\n")

                    f_md.write(final_raw_text)
                    f_txt.write(final_raw_text)
                    
                    f_md.write("\n\n---\n\n")
                    f_txt.write("\n\n" + "="*80 + "\n\n")

    except Exception as e:
        print(f"Error writing to file: {e}")
        sys.exit(1)

    if found_review_count == 0:
        print(f"\nNo reviews with parseable text fields were found.")
        try:
            os.remove(output_filename_md)
            os.remove(output_filename_txt)
        except OSError:
            pass
    else:
        print(f"\n✅ Success! All {found_review_count} reviews have been saved.")
        print(f"Markdown file: {output_filename_md}")
        print(f"Text file:     {output_filename_txt}")

if __name__ == "__main__":
    main()
