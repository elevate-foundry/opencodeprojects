#!/data/data/com.termux/files/usr/bin/bash
# fable-boot.sh — start Fable services at device boot (requires Termux:Boot app).
# Install: cp this file to ~/.termux/boot/
termux-wake-lock 2>/dev/null
# audit proxy
pgrep -f audit_proxy.py >/dev/null || nohup python3 "$HOME/opencodeprojects/proxy/audit_proxy.py" --port 8377 >> "$HOME/.fable/proxy.out" 2>&1 &
sleep 3
# AI chat bridge
pgrep -f xmpp-agent-bridge.py >/dev/null || nohup python3 "$HOME/.fable/skills/xmpp-agent-bridge/xmpp-agent-bridge.py" >> "$HOME/.fable/xmpp-bridge.out" 2>&1 &
