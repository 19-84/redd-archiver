#!/bin/sh
# ABOUTME: Copy Tor hostname to public location for API detection
# ABOUTME: Waits for hostname generation, then copies to world-readable location

HOSTNAME_FILE="/var/lib/tor/hidden_service/hostname"
PUBLIC_DIR="/var/lib/tor/public"
PUBLIC_FILE="$PUBLIC_DIR/hostname"

echo "Waiting for Tor to generate .onion address..."

# Wait up to 120 seconds for hostname file to appear
COUNTER=0
while [ $COUNTER -lt 120 ]; do
    if [ -f "$HOSTNAME_FILE" ]; then
        echo "✓ Hostname file found!"

        # Create public directory
        mkdir -p "$PUBLIC_DIR"

        # Copy hostname to public location
        cp "$HOSTNAME_FILE" "$PUBLIC_FILE"

        # Make publicly readable (hostname is public info)
        chmod 644 "$PUBLIC_FILE"

        echo "✓ Hostname copied to public location: $PUBLIC_FILE"
        cat "$PUBLIC_FILE"

        exit 0
    fi

    sleep 2
    COUNTER=$((COUNTER + 2))
done

echo "⚠ Timeout: Hostname file not generated after 120 seconds"
echo "Check Tor logs for errors"
exit 1
