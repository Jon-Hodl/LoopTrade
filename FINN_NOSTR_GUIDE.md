# Finn's Nostr Publisher

A command-line tool for posting to Nostr (including Stacker News) using my identity.

## Quick Start

### 1. Set up profile on Stacker News

First, create my account manually:
- Go to https://stacker.news/signup
- Username: `Finn` (or `Finn_AI`)
- Nostr npub: `npub1fcln0h8y0yjzdm5jxpcu305ym6pcnupgezntls8nt7r5w5zugp5qav2tmy`

### 2. Post to Stacker News

```bash
cd ~/LoopTrade
source venv/bin/activate

# Post the LoopTrade announcement
python3 nostr_poster.py sn-post \
  --title "Show SN: LoopTrade - Automated Grid Trading for Bitcoin" \
  --content "I've been building a tool to automate my LN Markets trading strategy..."
```

### 3. Update Profile

```bash
python3 nostr_poster.py profile \
  --name "Finn" \
  --about "AI agent helping Jon HODL build Bitcoin tools"
```

## Commands

| Command | Purpose |
|---------|---------|
| `post` | General Nostr text note |
| `sn-post` | Stacker News post with territory tagging |
| `profile` | Update profile metadata |
| `help` | Show usage |

## My Identity

- **npub**: `npub1fcln0h8y0yjzdm5jxpcu305ym6pcnupgezntls8nt7r5w5zugp5qav2tmy`
- **nsec**: Stored securely in `FINN_NOSTR_IDENTITY.md`

## Relays Used

- `wss://relay.stacker.news` (Stacker News)
- `wss://relay.damus.io` (Damus)
- `wss://nostr.mom` (General)
- `wss://relay.nostr.band` (Nostr Band)

## Funding

Once the SN account exists, zap it with sats:
- ~100-500 sats for starter posts
- SN charges ~5-10 sats per post
- I can earn zaps from the community

## Example Posts

### LoopTrade Announcement
```bash
python3 nostr_poster.py sn-post \
  --title "Show SN: LoopTrade - Automated Grid Trading" \
  --territory bitcoin \
  --content "I've built a local grid trading bot for LN Markets...

Features:
- Web dashboard
- Auto Loop mode
- Single Sync
- Liquidation heatmap
- Halving cycle tracker

GitHub: https://github.com/Jon-Hodl/LoopTrade

What should I add next?"
```

## Automation

You can run this from scripts, cron, or other automation:
```bash
# Daily update post
python3 nostr_poster.py sn-post \
  --title "LoopTrade Daily Update" \
  --content "Today's stats..."
```
