#!/bin/sh
# ABOUTME: Display .onion hostname on Tor container startup
# ABOUTME: Shows the hidden service address in logs for easy discovery

HOSTNAME_FILE="/var/lib/tor/hidden_service/hostname"

echo "========================================="
echo "Tor Hidden Service Status"
echo "========================================="

if [ -f "$HOSTNAME_FILE" ]; then
    ONION_ADDRESS=$(cat "$HOSTNAME_FILE")
    echo ""
    echo "✓ Tor hidden service is ready!"
    echo ""
    echo "Your .onion address:"
    echo "  $ONION_ADDRESS"
    echo ""
    echo "Access your archive via Tor Browser:"
    echo "  http://$ONION_ADDRESS"
    echo ""
    echo "Keys location: ./tor-hidden-service/"
    echo "IMPORTANT: Backup this directory to preserve your .onion address"
    echo ""
    echo "========================================="
else
    echo ""
    echo "⚠ Hostname file not found yet"
    echo ""
    echo "Tor is generating hidden service keys..."
    echo "This usually takes 30-60 seconds on first run."
    echo ""
    echo "Check again in a moment:"
    echo "  docker compose logs tor | grep 'Your .onion address'"
    echo ""
    echo "========================================="
fi
