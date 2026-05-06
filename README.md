# J.A.R.V.I.S. — AI Assistant
**Just A Rather Very Intelligent System** | Powered by Claude AI

---

## What this does

A fully voice-controlled AI assistant that:
- Wakes up when you say "Jarvis" (optional wake word)
- Listens to your voice via microphone
- Executes commands directly (open apps, check weather, set timers, etc.)
- Sends everything else to Claude AI for intelligent responses
- Speaks back using your system voice or ElevenLabs (cinematic quality)
- Remembers conversations across sessions

---

## Step 1 — Get your Claude API key

1. Go to **https://console.anthropic.com**
2. Sign up or log in with your email
3. Click **"API Keys"** in the left sidebar
4. Click **"Create Key"** — give it a name like "Jarvis"
5. Copy the key — it starts with `sk-ant-...`
6. Add credits: go to **Billing → Add Credits** — $5 is enough to run Jarvis for months

**Cost estimate for Jarvis:**
- Claude Sonnet 4.6: $3 per million input tokens / $15 per million output tokens
- A typical voice conversation uses ~500 tokens per exchange
- $5 credit = roughly 3,000 exchanges — about 3 months of daily use

---

## Step 2 — Install prerequisites

### Python
Make sure you have Python 3.10 or later:
```bash
python --version
```
Download from https://python.org if needed.

### System audio libraries

**Windows:** No extra steps needed.

**macOS:**
```bash
brew install portaudio mpg123
```

**Ubuntu / Debian Linux:**
```bash
sudo apt update
sudo apt install portaudio19-dev python3-pyaudio mpg123 espeak
```

---

## Step 3 — Set up the project

```bash
# 1. Navigate into the folder
cd jarvis

# 2. (Recommended) Create a virtual environment
python -m venv venv

# Activate it:
# Windows:
venv\Scripts\activate
# Mac / Linux:
source venv/bin/activate

# 3. Install all dependencies
pip install -r requirements.txt

# 4. Create your .env file
cp .env.example .env

# 5. Open .env and add your Anthropic API key
# (Use any text editor — Notepad, VS Code, nano, etc.)
```

---

## Step 4 — Configure .env

Open the `.env` file and fill in at minimum:

```
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here
USER_NAME=sir          # What Jarvis calls you
CITY=Mumbai            # Your city for weather
```

Everything else is optional — Jarvis works without them.

---

## Step 5 — Run Jarvis

```bash
python jarvis.py
```

By default (no Porcupine key), press **ENTER** to activate Jarvis, then speak.
With a Porcupine key, just say "Jarvis" out loud to activate.

---

## Voice commands Jarvis understands

### Time & information
| You say | Jarvis does |
|---------|-------------|
| "What time is it?" | Tells you the current time |
| "What's today's date?" | Tells you the date |
| "What's the weather?" | Current weather for your city |
| "Weather in Delhi" | Weather for a specific city |
| "System stats" | CPU, RAM, disk, battery usage |

### App control
| You say | Jarvis does |
|---------|-------------|
| "Open Spotify" | Launches Spotify |
| "Open Chrome" | Launches Chrome |
| "Open VS Code" | Launches VS Code |
| "Open Calculator" | Launches Calculator |

### Web
| You say | Jarvis does |
|---------|-------------|
| "Search for Python tutorials" | Google search |
| "Open YouTube" | Opens YouTube |
| "Open YouTube and search for lo-fi music" | YouTube search |

### Utilities
| You say | Jarvis does |
|---------|-------------|
| "Set a timer for 5 minutes" | Countdown timer with voice alert |
| "Set a timer for 30 seconds" | Short timer |
| "Take a screenshot" | Saves timestamped PNG |
| "Volume 50" | Sets system volume to 50% |
| "Mute volume" | Mutes system audio |

### Memory
| You say | Jarvis does |
|---------|-------------|
| "Clear memory" | Resets conversation history |

### Everything else
Any question, task, or conversation → sent to Claude AI for a smart response.

---

## Optional upgrades

### Wake word ("Hey Jarvis")
1. Go to **https://console.picovoice.ai** — free account
2. Create an **Access Key**
3. Add to `.env`: `PORCUPINE_KEY=your_key_here`
4. Jarvis will now passively listen and activate only when you say "Jarvis"

### Cinematic Jarvis voice (ElevenLabs)
1. Go to **https://elevenlabs.io** — free tier: 10,000 chars/month
2. Go to **Profile → API Key**
3. Add to `.env`: `ELEVENLABS_KEY=your_key_here`
4. Browse voices at elevenlabs.io/voice-library — find a deep British male voice
5. Copy its ID and add: `ELEVENLABS_VOICE_ID=paste_id_here`

### Weather
1. Go to **https://openweathermap.org/api** — free account
2. Copy your API key
3. Add to `.env`: `OPENWEATHER_KEY=your_key_here`

---

## Project structure

```
jarvis/
├── jarvis.py            ← Main application
├── requirements.txt     ← Python dependencies
├── .env.example         ← Template for your keys
├── .env                 ← Your actual keys (never share this)
├── jarvis_memory.json   ← Auto-created: conversation memory
└── jarvis.log           ← Auto-created: activity log
```

---

## Troubleshooting

**"No module named 'pyaudio'"**
- Windows: `pip install pipwin && pipwin install pyaudio`
- Mac: `brew install portaudio && pip install pyaudio`
- Linux: `sudo apt install python3-pyaudio`

**"ANTHROPIC_API_KEY not set"**
- Make sure your `.env` file exists (not `.env.example`) and has your real key

**Jarvis doesn't hear me**
- Check your microphone is set as default input in system settings
- Speak clearly and wait for "[Listening...]" before talking

**ElevenLabs not playing audio on Linux**
- Install mpg123: `sudo apt install mpg123`

---

## Security notes

- Your `.env` file contains sensitive API keys — never share it or push it to GitHub
- Add `.env` to your `.gitignore` if using Git
- Your conversations are sent to Anthropic's servers for processing — same as using Claude.ai

---

## Cost tracking

Monitor your API usage at: **https://console.anthropic.com → Usage**

You can set monthly spend limits in the billing settings to prevent surprise charges.
