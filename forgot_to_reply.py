"""
Forgot to Reply - Gmail Scanner
Finds emails you probably should have responded to.

Setup:
1. Go to https://console.cloud.google.com/
2. Create a project and enable Gmail API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download credentials.json to this directory
5. pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
6. Run this script
"""

import os
import json
import base64
import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Get the directory where this script lives
SCRIPT_DIR = Path(__file__).parent.resolve()

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# === SCORING CONFIG ===
ACTION_PHRASES = [
    ('let me know', 25), ('thoughts?', 30), ('what do you think', 28),
    ('can you', 20), ('could you', 20), ('would you', 18),
    ('please', 10), ('asap', 35), ('urgent', 35), ('waiting', 25),
    ('get back to me', 30), ('reply', 25), ('respond', 25),
    ('following up', 30), ('checking in', 25), ('any update', 30),
    ('free to', 15), ('available', 12), ('when can', 22),
]

CLOSE_PHRASES = ['thanks', 'thank you', 'cheers', 'best', 'regards']


@dataclass
class ThreadAnalysis:
    thread_id: str
    subject: str
    sender_name: str
    sender_email: str
    last_message: str
    days_ago: int
    message_count: int
    is_read: bool
    score: int
    reasons: list[str]


def get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds = None
    
    # Use absolute paths based on script location
    token_path = SCRIPT_DIR / 'token.json'
    
    # Look for credentials file - try common names
    creds_file = None
    possible_names = ['credentials.json', 'client_secrets.json', 'client_secret.json']
    
    for name in possible_names:
        check_path = SCRIPT_DIR / name
        if check_path.exists():
            creds_file = check_path
            break
    
    if not creds_file:
        print("\n❌ ERROR: No credentials file found!")
        print(f"\nLooked in: {SCRIPT_DIR}")
        print("\nTo fix this:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a project (or select existing)")
        print("3. Search 'Gmail API' in the search bar and ENABLE it")
        print("4. Go to 'APIs & Services' → 'Credentials'")
        print("5. Click '+ CREATE CREDENTIALS' → 'OAuth client ID'")
        print("6. If prompted, configure consent screen (External, just add your email)")
        print("7. Application type: 'Desktop app', name it anything")
        print("8. Click 'Download JSON' on the created credential")
        print(f"9. Save it as 'credentials.json' in: {SCRIPT_DIR}")
        print("\nThen run this script again!")
        raise SystemExit(1)
    
    print(f"Using credentials from: {creds_file}")
    
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Load the JSON ourselves to bypass library bug
            with open(creds_file, 'r') as f:
                client_config = json.load(f)
            
            flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    
    return build('gmail', 'v1', credentials=creds)


def get_user_email(service) -> str:
    """Get the authenticated user's email address."""
    profile = service.users().getProfile(userId='me').execute()
    return profile['emailAddress'].lower()


def decode_body(payload) -> str:
    """Extract text body from email payload."""
    if 'body' in payload and payload['body'].get('data'):
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                if part['body'].get('data'):
                    return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
            elif 'parts' in part:
                result = decode_body(part)
                if result:
                    return result
    return ''


def extract_sender(headers: list) -> tuple[str, str]:
    """Extract sender name and email from headers."""
    for h in headers:
        if h['name'].lower() == 'from':
            val = h['value']
            match = re.match(r'(.+?)\s*<(.+?)>', val)
            if match:
                return match.group(1).strip('" '), match.group(2).lower()
            return val, val.lower()
    return 'Unknown', 'unknown'


def extract_subject(headers: list) -> str:
    for h in headers:
        if h['name'].lower() == 'subject':
            return h['value']
    return '(No Subject)'


def score_message(text: str, days_ago: int, message_count: int) -> tuple[int, list[str]]:
    """Score how much a message needs a reply."""
    score = 0
    reasons = []
    text_lower = text.lower()
    
    # Question detection
    if '?' in text:
        score += 30
        reasons.append('Contains question')
    
    # Action phrases
    for phrase, weight in ACTION_PHRASES:
        if phrase in text_lower:
            score += weight
            reasons.append(f'Contains "{phrase}"')
            break  # Only count first match to avoid over-scoring
    
    # Time factor
    if days_ago > 30:
        score += 25
        reasons.append('Over a month old')
    elif days_ago > 14:
        score += 15
        reasons.append('Over 2 weeks old')
    elif days_ago > 7:
        score += 10
        reasons.append('Over a week old')
    
    # Thread length
    if message_count > 5:
        score += 15
        reasons.append('Long thread')
    elif message_count > 2:
        score += 8
        reasons.append('Active thread')
    
    # Closing phrases reduce score
    for phrase in CLOSE_PHRASES:
        if phrase in text_lower[-200:]:  # Check end of message
            score -= 15
            reasons.append('Has closing phrase (lower priority)')
            break
    
    return min(max(score, 0), 100), reasons


def analyze_thread(service, thread_id: str, user_email: str) -> Optional[ThreadAnalysis]:
    """Analyze a single thread to see if it needs a reply."""
    thread = service.users().threads().get(
        userId='me', id=thread_id, format='full'
    ).execute()
    
    messages = thread.get('messages', [])
    if not messages:
        return None
    
    last_msg = messages[-1]
    headers = last_msg['payload'].get('headers', [])
    
    sender_name, sender_email = extract_sender(headers)
    
    # Skip if last message is from us (we already replied)
    if sender_email == user_email:
        return None
    
    # Skip likely automated/noreply emails
    if any(x in sender_email for x in ['noreply', 'no-reply', 'notifications', 'mailer-daemon']):
        return None
    
    subject = extract_subject(headers)
    body = decode_body(last_msg['payload'])
    
    # Get snippet if body extraction failed
    if not body.strip():
        body = last_msg.get('snippet', '')
    
    # Truncate for display
    body_preview = body[:500].strip()
    if len(body) > 500:
        body_preview += '...'
    
    # Calculate age
    timestamp = int(last_msg['internalDate']) / 1000
    msg_date = datetime.fromtimestamp(timestamp)
    days_ago = (datetime.now() - msg_date).days
    
    # Check read status
    labels = last_msg.get('labelIds', [])
    is_read = 'UNREAD' not in labels
    
    score, reasons = score_message(body, days_ago, len(messages))
    
    return ThreadAnalysis(
        thread_id=thread_id,
        subject=subject,
        sender_name=sender_name,
        sender_email=sender_email,
        last_message=body_preview,
        days_ago=days_ago,
        message_count=len(messages),
        is_read=is_read,
        score=score,
        reasons=reasons
    )


def find_forgotten_replies(days_back: int = 60, max_results: int = 100) -> list[ThreadAnalysis]:
    """Main function to find emails needing replies."""
    print("Connecting to Gmail...")
    service = get_gmail_service()
    user_email = get_user_email(service)
    print(f"Scanning inbox for {user_email}...")
    
    # Search for emails in inbox from last N days
    after_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y/%m/%d')
    query = f'in:inbox after:{after_date}'
    
    results = service.users().threads().list(
        userId='me', q=query, maxResults=max_results
    ).execute()
    
    threads = results.get('threads', [])
    print(f"Found {len(threads)} threads to analyze...")
    
    needs_reply = []
    for i, t in enumerate(threads):
        if i % 10 == 0:
            print(f"  Analyzing thread {i+1}/{len(threads)}...")
        
        analysis = analyze_thread(service, t['id'], user_email)
        if analysis and analysis.score >= 20:  # Minimum threshold
            needs_reply.append(analysis)
    
    # Sort by score descending
    needs_reply.sort(key=lambda x: x.score, reverse=True)
    return needs_reply


def print_results(results: list[ThreadAnalysis]):
    """Pretty print results to console."""
    print("\n" + "="*60)
    print("🔴 EMAILS THAT PROBABLY NEED A REPLY")
    print("="*60 + "\n")
    
    for r in results[:20]:  # Top 20
        status = "📩 UNREAD" if not r.is_read else "📭"
        awkward = "😬" if r.score >= 70 else "😅" if r.score >= 50 else "🤔"
        
        print(f"{awkward} Score: {r.score}")
        print(f"   From: {r.sender_name} <{r.sender_email}>")
        print(f"   Subject: {r.subject}")
        print(f"   {status} | {r.days_ago} days ago | {r.message_count} messages")
        print(f"   Why: {', '.join(r.reasons[:3])}")
        print(f"   Preview: {r.last_message[:100]}...")
        print()


def export_json(results: list[ThreadAnalysis], filename: str = 'forgotten_replies.json'):
    """Export results to JSON for use with frontend."""
    data = [
        {
            'id': r.thread_id,
            'from': r.sender_name,
            'email': r.sender_email,
            'subject': r.subject,
            'lastMessage': r.last_message,
            'daysAgo': r.days_ago,
            'messageCount': r.message_count,
            'isRead': r.is_read,
            'score': r.score,
            'reasons': r.reasons,
        }
        for r in results
    ]
    
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"\nExported {len(data)} results to {filename}")


if __name__ == '__main__':
    results = find_forgotten_replies(days_back=60, max_results=150)
    print_results(results)
    export_json(results)