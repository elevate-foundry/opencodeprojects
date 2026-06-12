#!/data/data/com.termux/files/usr/bin/bash
# Start the XMPP listener if not already running.
pgrep -f xmpp-listen.py >/dev/null && { echo "already running"; exit 0; }
nohup python3 "$HOME/.fable/skills/xmpp-listen/xmpp-listen.py" >> "$HOME/.fable/xmpp-listener.out" 2>&1 &
echo "started pid=$!"
