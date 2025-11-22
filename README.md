# 📬 Forgot to Reply

**Find emails you accidentally left hanging.**

A Python tool that scans your Gmail inbox and identifies emails that probably need a response — using NLP-style scoring to detect questions, action requests, and awkward silence.

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## The Problem

You read an email, think "I'll respond later," and then... you don't. Days pass. Weeks pass. That person is still waiting.

This tool finds those emails by analyzing:
- **Questions left unanswered** ("Can you...?", "What do you think?")
- **Action phrases** ("Let me know", "Following up", "Any update?")
- **Time decay** (older = more awkward)
- **Thread context** (ongoing conversations are higher priority)

## Sample Output

```
============================================================
🔴 EMAILS THAT PROBABLY NEED A REPLY
============================================================

😬 Score: 85
   From: Sarah Chen <sarah@company.com>
   Subject: Re: Project timeline update
   📭 | 12 days ago | 6 messages
   Why: Contains question, Contains "let me know", Over a week old
   Preview: Can you send me the revised timeline when you get a chance?...

😅 Score: 62
   From: Mom <mom@email.com>
   Subject: Thanksgiving plans??
   📭 | 23 days ago | 2 messages
   Why: Contains question, Over 2 weeks old
   Preview: Are you coming home for Thanksgiving this year?...
```

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/forgot-to-reply.git
cd forgot-to-reply
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up Gmail API credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the **Gmail API** (search for it)
4. Go to **APIs & Services → Credentials**
5. Click **+ CREATE CREDENTIALS → OAuth client ID**
6. Configure consent screen if prompted (External, add your email as test user)
7. Application type: **Desktop app**
8. Download the JSON file
9. Rename it to `credentials.json` and place in project root

### 4. Run it

```bash
python forgot_to_reply.py
```

First run opens a browser for Google authorization. After that, results appear in terminal and export to `forgotten_replies.json`.

## Configuration

Edit the constants at the top of `forgot_to_reply.py`:

```python
# How far back to scan (days)
DAYS_BACK = 60

# Max threads to analyze
MAX_RESULTS = 150

# Minimum score to include in results
MIN_SCORE = 20
```

### Scoring Weights

Customize what triggers a high score:

```python
ACTION_PHRASES = [
    ('let me know', 25),
    ('thoughts?', 30),
    ('following up', 30),
    ('urgent', 35),
    # Add your own...
]
```

## How Scoring Works

| Signal | Points |
|--------|--------|
| Contains a question (`?`) | +30 |
| "ASAP" or "urgent" | +35 |
| "Following up" / "checking in" | +30 |
| "Let me know" / "thoughts?" | +25-30 |
| Over 1 month old | +25 |
| Over 2 weeks old | +15 |
| Long thread (5+ messages) | +15 |
| Ends with "thanks" | -15 |

Final score capped at 100.

## Project Structure

```
forgot-to-reply/
├── forgot_to_reply.py    # Main script
├── requirements.txt      # Python dependencies
├── credentials.json      # Your Gmail API creds (gitignored)
├── token.json           # Auth token (auto-generated, gitignored)
├── forgotten_replies.json # Output (gitignored)
└── README.md
```

## Output

Results are saved to `forgotten_replies.json`:

```json
[
  {
    "id": "thread_abc123",
    "from": "Sarah Chen",
    "email": "sarah@company.com",
    "subject": "Re: Project timeline",
    "lastMessage": "Can you send me the revised timeline?...",
    "daysAgo": 12,
    "messageCount": 6,
    "isRead": true,
    "score": 85,
    "reasons": ["Contains question", "Contains \"let me know\""]
  }
]
```

## Privacy & Security

- **Read-only access**: Only requests `gmail.readonly` permission
- **Local processing**: All analysis happens on your machine
- **No data collection**: Nothing is sent anywhere except Google's API
- **Credentials stay local**: `credentials.json` and `token.json` are gitignored

## Roadmap

- [x] Gmail scanning
- [x] Configurable scoring
- [x] JSON export
- [ ] Chrome extension
- [ ] Daily digest emails
- [ ] iMessage support (macOS)
- [ ] Slack integration
- [ ] Web dashboard

## Contributing

PRs welcome! Some ideas:
- Better NLP for question detection
- Support for other email providers
- Smarter filtering (ignore newsletters, etc.)

## License

MIT — do whatever you want with it.

---

**Stop ghosting people by accident.** ✉️