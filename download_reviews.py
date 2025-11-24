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
        
        # We return ALL replies, filtering out the original submission.
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

# --- NEW HELPER FUNCTION ---
def extract_text_from_value(content_item):
    """
    Extracts text from various OpenReview value formats.
    e.g., "string", {"value": "string"}, {"value": 8}, {"value": ["list"]}
    """
    extracted_text = None
    
    # 1. Check for {"value": ...} structure
    if isinstance(content_item, dict) and 'value' in content_item:
        value = content_item['value']
        if isinstance(value, str):
            extracted_text = value
        elif isinstance(value, (int, float)):
            extracted_text = str(value)
        elif isinstance(value, list):
            extracted_text = ", ".join(str(v) for v in value)
    
    # 2. Check for direct "key": "string" structure
    elif isinstance(content_item, str):
        extracted_text = content_item
        
    if extracted_text and extracted_text.strip():
        return extracted_text
    return None

def main():
    parser = argparse.ArgumentParser(
        description="Download OpenReview reviews as raw text and Markdown.",
        epilog="Example (URL): python download_reviews.py --email u@x.com --url 'https://openreview.net/forum?id=...'\n" \
               "Example (Manual): python download_reviews.py --email u@x.com --forum_id '...-f_id' --venue_id 'Conf.org/Year/Venue'"
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
    
    # --- UPDATED: Comprehensive list of keys for AISTATS, ICLR, NeurIPS, etc. ---
    text_field_keys = [
        # Standard
        'review', 'comment', 
        
        # Summaries
        'summary', 'summary_of_review', 'summary_and_contributions',
        
        # Content Fields
        'strengths', 'weaknesses', 'limitations', 'questions',
        'clarity', 'relation_to_prior_work', 'reproducibility',
        'novelty', 'significance',
        
        # Justifications (AISTATS style)
        'soundness_justification',
        'significance_justification',
        'novelty_justification',
        'technical_quality_justification',
        'empirical_evaluation_justification',
        
        # Scores (checked last so text appears first usually)
        'rating', 'confidence', 'recommendation', 
        'soundness', 'presentation', 'contribution',
        
        # Ethics
        'flag_for_ethics_review', 'details_of_ethics_concerns', 'code_of_conduct',
    ]
    
    try:
        with open(output_filename_md, 'w', encoding='utf-8') as f_md, \
             open(output_filename_txt, 'w', encoding='utf-8') as f_txt:
            
            for i, note in enumerate(replies):
                
                raw_text_parts = []
                
                # Create a lowercase mapping of the note's content keys
                # This handles 'Summary And Contributions' -> 'summary and contributions'
                content_keys_lower = {k.lower().replace('_', ' '): k for k in note.content.keys()}
                
                # Check for keys in our priority list
                for key_to_find in text_field_keys:
                    
                    # Normalize key to find (handle spaces vs underscores)
                    key_to_find_spaces = key_to_find.replace('_', ' ')
                    
                    # Check if this key exists in the note
                    found_key = None
                    if key_to_find in content_keys_lower:
                        found_key = content_keys_lower[key_to_find]
                    elif key_to_find_spaces in content_keys_lower:
                        found_key = content_keys_lower[key_to_find_spaces]
                        
                    if found_key:
                        content_item = note.content[found_key]
                        extracted_text = extract_text_from_value(content_item)
                        
                        if extracted_text:
                            # Format title
                            title = found_key.replace('_', ' ').title()
                            
                            # For simple keys like "Review", skip title
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
