# Gemini AI Setup Guide

This guide explains how to enable Gemini AI for intelligent heat pump optimization.

## What is Gemini?

Gemini 2.5 Flash is Google's latest AI model, optimized for:
- **Fast responses** - Low latency for real-time analysis
- **Cost-effective** - $0.30 per 1M input tokens (40x cheaper than Claude)
- **Powerful reasoning** - Excellent for complex optimization decisions
- **Large context** - 1M token context window
- **Free tier** - 15 requests/minute free

## Getting Your API Key

1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click **"Get API key"** or **"Create API key"**
4. Copy the API key (starts with `AIza...`)

## Configuration

### Add API Key to .env

Edit `/home/peccz/AI/nibe_autotuner/.env`:

```bash
# AI/ML - Google Gemini
GOOGLE_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### Restart Services

```bash
# Restart mobile app (includes AI agent)
sudo systemctl restart nibe-mobile

# Verify it's running
sudo systemctl status nibe-mobile
```

## Features

### 1. AI-Powered Optimization Suggestions

The optimizer will automatically use Gemini to:
- Analyze heat pump performance (COP, Delta T, comfort)
- Compare with yesterday's metrics
- Review recent parameter changes
- Generate intelligent recommendations

**Fallback:** If Gemini is unavailable, the system automatically falls back to rule-based optimization.

### 2. Interactive Chat

Visit http://100.100.118.62:8502/ai-agent to:
- Ask questions about heat pump performance
- Get explanations of metrics
- Request optimization advice
- Understand energy savings

Example questions:
- "Hur kan jag förbättra COP?"
- "Varför är gradminuterna höga?"
- "Vad betyder Delta T?"

### 3. Performance Analysis

The AI analyzes:
- **Current metrics:** COP, degree minutes, Delta T, temperatures
- **Trends:** Comparison with yesterday's performance
- **History:** Recent parameter changes and their effects
- **Context:** Outdoor temperature, system state, runtime patterns

## Pricing & Usage

### Free Tier
- **15 requests/minute**
- **1,500 requests/day**
- Perfect for personal use

### Estimated Usage
- Dashboard loads: ~2-3 requests/day
- Chat messages: ~5-10 requests/day
- Auto-optimization: ~2 requests/day

**Total:** ~10-15 requests/day → **100% FREE** within quota

### Paid Usage
If you exceed free tier:
- Input: $0.30 per 1M tokens (~$0.0003 per request)
- Output: $2.50 per 1M tokens (~$0.001 per request)

**Monthly cost estimate:** $0.05 - $0.20 (basically free)

## API Endpoints

### `/api/gemini/chat`
Interactive chat with AI agent.

**Request:**
```json
{
  "message": "Hur kan jag förbättra COP?",
  "history": []
}
```

**Response:**
```json
{
  "success": true,
  "response": "För att förbättra COP kan du..."
}
```

### `/api/gemini/analyze`
Get full analysis and recommendations.

**Request:**
```json
{
  "hours": 24
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "recommendations": [...],
    "analysis": "Overall system status...",
    "status": "good|warning|critical"
  }
}
```

## Troubleshooting

### Error: "AI-funktionen är inte aktiverad"

**Solution:** Add `GOOGLE_API_KEY` to `.env` and restart:
```bash
sudo systemctl restart nibe-mobile
```

### Error: "API key not valid"

**Solution:**
1. Verify your API key in [AI Studio](https://aistudio.google.com/app/apikey)
2. Make sure it starts with `AIza`
3. Check for extra spaces or line breaks in `.env`

### Error: "Resource exhausted"

**Solution:** You've hit the free tier rate limit (15 req/min). Wait 60 seconds and try again.

### Fallback to Rule-Based System

If Gemini fails, the system automatically uses rule-based optimization:
```
AI suggestions failed, falling back to rules: [error message]
```

This ensures the system **always works**, even without AI.

## Security

- API keys are stored in `.env` (git-ignored)
- Never commit `.env` to GitHub
- Rotate keys periodically
- Use environment-specific keys (dev/prod)

## Performance

Typical response times:
- Chat queries: 1-3 seconds
- Analysis requests: 2-5 seconds
- Optimization suggestions: 2-4 seconds

## Comparison: Gemini vs Claude

| Feature | Gemini 2.5 Flash | Claude 3.5 Sonnet |
|---------|------------------|-------------------|
| **Cost** | $0.30 / 1M tokens | $3.00 / 1M tokens |
| **Speed** | Fast (~2s) | Slower (~4s) |
| **Context** | 1M tokens | 200k tokens |
| **Free tier** | 15 req/min | None |
| **Reasoning** | Excellent | Excellent |
| **Safety** | Good | Excellent |

**For this use case:** Gemini wins on cost, speed, and free tier.

## Support

If you need help:
1. Check logs: `sudo journalctl -u nibe-mobile -f`
2. Verify API key is set: `grep GOOGLE_API_KEY .env`
3. Test manually: `PYTHONPATH=./src python3 -c "from gemini_agent import GeminiAgent; print('OK')"`

## Sources

- [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini 2.5 Flash Announcement](https://blog.google/technology/google-deepmind/gemini-model-thinking-updates-march-2025/)
- [Google AI Studio](https://aistudio.google.com/)
