#!/usr/bin/env python3
"""
Finn's Nostr Publisher Tool
Posts events to Nostr relays (including Stacker News)
"""

import asyncio
import json
import sys
from datetime import datetime
from pynostr.key import PrivateKey
from pynostr.event import Event
from pynostr.relay_manager import RelayManager

# Finn's Nostr identity
NSEC = "nsec1mkduq8slcsmcu7jgc5zcvnjpr94vj086k80jgxpm22che8lcy0eqdkpl4a"
NPUB = "npub1fcln0h8y0yjzdm5jxpcu305ym6pcnupgezntls8nt7r5w5zugp5qav2tmy"

# Default relays (including Stacker News)
DEFAULT_RELAYS = [
    "wss://relay.stacker.news",      # Stacker News primary
    "wss://relay.damus.io",           # Damus relay
    "wss://nostr.mom",                # General relay
    "wss://relay.nostr.band",         # Nostr band
]

class NostrPoster:
    def __init__(self, nsec=NSEC):
        self.private_key = PrivateKey.from_nsec(nsec)
        self.public_key = self.private_key.public_key
        self.npub = self.public_key.bech32()
        self.relay_manager = None
        
    async def connect(self, relays=None):
        """Connect to Nostr relays"""
        if relays is None:
            relays = DEFAULT_RELAYS
            
        self.relay_manager = RelayManager()
        
        for relay_url in relays:
            try:
                self.relay_manager.add_relay(relay_url)
                print(f"✓ Connected to {relay_url}")
            except Exception as e:
                print(f"✗ Failed to connect to {relay_url}: {e}")
        
        # Give connections time to establish
        await asyncio.sleep(2)
        
    def create_text_note(self, content, reply_to=None):
        """Create a text note event (kind 1)"""
        event = Event(
            kind=1,
            content=content,
            tags=[]
        )
        
        # Add reply tags if replying to another event
        if reply_to:
            # reply_to should be dict with 'id' and 'pubkey'
            event.tags.append(["e", reply_to['id'], "", "root"])
            event.tags.append(["p", reply_to['pubkey']])
        
        return event
    
    def create_metadata_event(self, name, about, picture=None):
        """Create metadata event (kind 0) for profile"""
        metadata = {
            "name": name,
            "about": about,
            "display_name": name,
        }
        if picture:
            metadata["picture"] = picture
            
        event = Event(
            kind=0,
            content=json.dumps(metadata),
            tags=[]
        )
        return event
    
    async def publish(self, event):
        """Sign and publish an event"""
        # Sign the event
        event.sign(self.private_key.hex())
        
        print(f"\nPublishing event:")
        print(f"  Kind: {event.kind}")
        print(f"  Content preview: {event.content[:100]}...")
        print(f"  Event ID: {event.id[:16]}...")
        
        # Publish to all connected relays
        if self.relay_manager:
            self.relay_manager.publish_event(event)
            print(f"  ✓ Published to {len(self.relay_manager.relays)} relays")
            
            # Give relays time to receive
            await asyncio.sleep(1)
        else:
            print("  ✗ No relay manager connected")
            
        return event.id
    
    async def post_to_stacker_news(self, title, content, territory="bitcoin"):
        """
        Post to Stacker News
        Note: SN uses a proprietary format for posts, but accepts Nostr events
        This creates a kind 1 event that SN should pick up
        """
        # Combine title and content
        full_content = f"{title}\n\n{content}"
        
        # Add territory tag for SN
        event = Event(
            kind=1,
            content=full_content,
            tags=[["t", territory]]  # Tag with territory
        )
        
        event_id = await self.publish(event)
        return event_id
    
    async def close(self):
        """Close relay connections"""
        if self.relay_manager:
            self.relay_manager.close_all_relay_connections()
            print("\n✓ Closed all relay connections")


def print_help():
    print("""
Finn's Nostr Publisher Tool

Usage:
  python nostr_poster.py post "Your message here"
  python nostr_poster.py post --title "Title" --content "Body text"
  python nostr_poster.py sn-post --title "Stacker News Title" --content "Post body"
  python nostr_poster.py profile --name "Finn" --about "AI agent"
  
Options:
  --relay URL    Add a custom relay (can use multiple)
  --reply-to ID  Reply to an existing event
  --territory    Stacker News territory (default: bitcoin)
""")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Finn's Nostr Publisher")
    parser.add_argument("command", choices=["post", "sn-post", "profile", "help"])
    parser.add_argument("--title", help="Post title")
    parser.add_argument("--content", help="Post content")
    parser.add_argument("--relay", action="append", help="Custom relay URL")
    parser.add_argument("--reply-to", help="Event ID to reply to")
    parser.add_argument("--territory", default="bitcoin", help="SN territory")
    parser.add_argument("--name", default="Finn", help="Profile name")
    parser.add_argument("--about", default="AI agent helping Jon HODL", help="Profile bio")
    
    args = parser.parse_args()
    
    if args.command == "help":
        print_help()
        return
    
    # Initialize poster
    poster = NostrPoster()
    print(f"Finn's Nostr Publisher")
    print(f"npub: {poster.npub}\n")
    
    # Connect to relays
    relays = args.relay if args.relay else None
    await poster.connect(relays)
    
    try:
        if args.command == "post":
            if args.title and args.content:
                content = f"{args.title}\n\n{args.content}"
            elif args.content:
                content = args.content
            else:
                content = " ".join(args.content) if isinstance(args.content, list) else args.content or "Test post from Finn"
            
            event = poster.create_text_note(content)
            event_id = await poster.publish(event)
            print(f"\n✓ Posted! Event ID: {event_id}")
            
        elif args.command == "sn-post":
            if not args.title:
                print("Error: --title required for Stacker News posts")
                return
                
            event_id = await poster.post_to_stacker_news(
                title=args.title,
                content=args.content or "",
                territory=args.territory
            )
            print(f"\n✓ Posted to Stacker News! Event ID: {event_id}")
            
        elif args.command == "profile":
            event = poster.create_metadata_event(
                name=args.name,
                about=args.about
            )
            event_id = await poster.publish(event)
            print(f"\n✓ Profile updated! Event ID: {event_id}")
            
    finally:
        await poster.close()


if __name__ == "__main__":
    asyncio.run(main())
