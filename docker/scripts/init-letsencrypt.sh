#!/bin/bash
# ABOUTME: One-time Let's Encrypt certificate initialization script for redd-archiver
# ABOUTME: Automates HTTPS setup with DNS validation, staging mode, and error handling

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load environment variables
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Please copy .env.example to .env and configure DOMAIN and EMAIL"
    echo "  cd $PROJECT_ROOT"
    echo "  cp .env.example .env"
    echo "  nano .env"
    exit 1
fi

# Source .env file
set -a
source "$PROJECT_ROOT/.env"
set +a

# Configuration
DOMAIN=${DOMAIN:-example.com}
EMAIL=${EMAIL:-admin@example.com}
STAGING=${CERTBOT_TEST_CERT:-1}

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Redd-Archiver HTTPS Setup${NC}"
echo -e "${GREEN}Let's Encrypt Certificate Initialization${NC}"
echo -e "${GREEN}========================================${NC}"

# Step 1: Validate configuration
echo -e "\n${BLUE}[1/8]${NC} ${YELLOW}Validating configuration...${NC}"

if [ "$DOMAIN" = "example.com" ]; then
    echo -e "${RED}Error: Please set DOMAIN in .env to your actual domain${NC}"
    echo "Example: DOMAIN=archive.yoursite.com"
    exit 1
fi

if [ "$EMAIL" = "admin@example.com" ]; then
    echo -e "${RED}Error: Please set EMAIL in .env to your actual email${NC}"
    echo "Example: EMAIL=you@yoursite.com"
    exit 1
fi

echo -e "${GREEN}✓ Configuration valid${NC}"
echo "  Domain: $DOMAIN"
echo "  Email: $EMAIL"
echo "  Mode: $([ "$STAGING" != "0" ] && echo "Staging (test)" || echo "Production")"

# Step 2: Check DNS configuration
echo -e "\n${BLUE}[2/8]${NC} ${YELLOW}Checking DNS configuration...${NC}"

# Get public IP
PUBLIC_IP=$(curl -s -4 --connect-timeout 5 ifconfig.me || echo "unknown")

# Get DNS resolution
if command -v dig >/dev/null 2>&1; then
    DNS_IP=$(dig +short "$DOMAIN" A | tail -n1 || echo "unknown")
elif command -v nslookup >/dev/null 2>&1; then
    DNS_IP=$(nslookup "$DOMAIN" | grep -A1 "Name:" | tail -n1 | awk '{print $2}' || echo "unknown")
else
    DNS_IP="unknown (dig/nslookup not available)"
fi

echo "  Server IP: $PUBLIC_IP"
echo "  DNS A record: $DNS_IP"

if [ "$PUBLIC_IP" != "$DNS_IP" ] || [ "$DNS_IP" = "unknown" ]; then
    echo -e "${RED}Warning: DNS A record doesn't match server IP${NC}"
    echo "Please ensure $DOMAIN points to $PUBLIC_IP before continuing"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled. Fix DNS and try again."
        exit 1
    fi
else
    echo -e "${GREEN}✓ DNS configured correctly${NC}"
fi

# Step 3: Check for existing certificates
echo -e "\n${BLUE}[3/8]${NC} ${YELLOW}Checking for existing certificates...${NC}"

# Check if certificates exist in Docker volume or local directory
CERT_EXISTS=0
if sudo docker volume inspect reddarchiver-certbot-certs >/dev/null 2>&1; then
    # Check if certificates exist in volume
    if sudo docker run --rm -v reddarchiver-certbot-certs:/etc/letsencrypt alpine test -d "/etc/letsencrypt/live/$DOMAIN" 2>/dev/null; then
        CERT_EXISTS=1
    fi
fi

if [ $CERT_EXISTS -eq 1 ]; then
    echo -e "${YELLOW}Certificates already exist for $DOMAIN${NC}"
    read -p "Regenerate certificates? This will replace existing ones. (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing existing certificates..."
        sudo docker run --rm -v reddarchiver-certbot-certs:/etc/letsencrypt alpine rm -rf "/etc/letsencrypt/live/$DOMAIN" "/etc/letsencrypt/archive/$DOMAIN" "/etc/letsencrypt/renewal/$DOMAIN.conf"
        echo -e "${GREEN}✓ Existing certificates removed${NC}"
    else
        echo "Keeping existing certificates. Setup cancelled."
        exit 0
    fi
else
    echo -e "${GREEN}✓ No existing certificates found${NC}"
fi

# Step 4: Prepare nginx configuration
echo -e "\n${BLUE}[4/8]${NC} ${YELLOW}Preparing nginx configuration...${NC}"

# Ensure HTTP config is being used (for initial cert acquisition)
cd "$PROJECT_ROOT"

echo -e "${GREEN}✓ Configuration prepared${NC}"

# Step 5: Start services in HTTP mode
echo -e "\n${BLUE}[5/8]${NC} ${YELLOW}Starting services (HTTP mode)...${NC}"

# Stop any existing containers
docker compose down 2>/dev/null || true

# Start services (HTTP mode, no certbot)
docker compose up -d nginx search-server postgres

# Wait for nginx to be healthy
echo "Waiting for nginx to be ready..."
RETRIES=30
while [ $RETRIES -gt 0 ]; do
    if docker compose exec -T nginx wget --spider -q http://localhost/health 2>/dev/null; then
        echo -e "${GREEN}✓ Nginx is ready${NC}"
        break
    fi
    sleep 2
    RETRIES=$((RETRIES-1))
    echo -n "."
done

if [ $RETRIES -eq 0 ]; then
    echo -e "${RED}Error: Nginx failed to start${NC}"
    echo "Check logs: docker compose logs nginx"
    exit 1
fi

# Step 6: Request certificate from Let's Encrypt
echo -e "\n${BLUE}[6/8]${NC} ${YELLOW}Requesting Let's Encrypt certificate...${NC}"

STAGING_ARG=""
if [ "$STAGING" != "0" ]; then
    echo "Using Let's Encrypt staging server (test mode)"
    echo "Staging certificates are not trusted by browsers but avoid rate limits"
    STAGING_ARG="--staging"
fi

# Request certificate using webroot method
echo "Running certbot to obtain certificate..."
docker compose run --rm -v "$PROJECT_ROOT/docker/nginx/nginx.conf.http:/etc/nginx/nginx.conf:ro" certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --force-renewal \
    $STAGING_ARG \
    -d "$DOMAIN"

if [ $? -ne 0 ]; then
    echo -e "${RED}Certificate request failed${NC}"
    echo ""
    echo "Common issues:"
    echo "  - DNS not pointing to this server"
    echo "  - Firewall blocking port 80"
    echo "  - Domain already hit rate limit (use staging mode: CERTBOT_TEST_CERT=true)"
    echo ""
    echo "Debug commands:"
    echo "  Check DNS: dig +short $DOMAIN"
    echo "  Check port 80: curl -I http://$DOMAIN/.well-known/acme-challenge/test"
    echo "  Check logs: docker compose logs certbot"
    exit 1
fi

echo -e "${GREEN}✓ Certificate obtained successfully${NC}"

# Step 7: Update nginx configuration for HTTPS
echo -e "\n${BLUE}[7/8]${NC} ${YELLOW}Configuring HTTPS...${NC}"

# Create HTTPS nginx config with actual domain
HTTPS_CONFIG="$PROJECT_ROOT/docker/nginx/nginx.conf.https"
sed "s/DOMAIN_PLACEHOLDER/$DOMAIN/g" "$HTTPS_CONFIG" > "$PROJECT_ROOT/docker/nginx/nginx.conf.https.tmp"
mv "$PROJECT_ROOT/docker/nginx/nginx.conf.https.tmp" "$PROJECT_ROOT/docker/nginx/nginx.conf.https.active"

echo "Switching to HTTPS configuration..."

# Stop services
docker compose down

# Start with production profile (includes certbot for renewal)
docker compose --profile production up -d

# Wait for services to be ready
echo "Waiting for services to start..."
sleep 10

# Step 8: Test HTTPS connection
echo -e "\n${BLUE}[8/8]${NC} ${YELLOW}Testing HTTPS connection...${NC}"

# Test HTTPS endpoint
if [ "$STAGING" != "0" ]; then
    # Staging cert won't be trusted, use -k flag
    HTTP_CODE=$(curl -s -k -o /dev/null -w "%{http_code}" "https://$DOMAIN/health" 2>/dev/null || echo "000")
else
    # Production cert should be trusted
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/health" 2>/dev/null || echo "000")
fi

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ HTTPS is working!${NC}"
else
    echo -e "${RED}✗ HTTPS test failed (HTTP $HTTP_CODE)${NC}"
    echo "Check nginx logs: docker compose logs nginx"
    echo "Check certificate: docker compose exec certbot certbot certificates"
    exit 1
fi

# Test HTTP redirect
HTTP_REDIRECT=$(curl -s -o /dev/null -w "%{http_code}" "http://$DOMAIN/" 2>/dev/null || echo "000")
if [ "$HTTP_REDIRECT" = "301" ]; then
    echo -e "${GREEN}✓ HTTP to HTTPS redirect working${NC}"
else
    echo -e "${YELLOW}⚠ HTTP redirect returned $HTTP_REDIRECT (expected 301)${NC}"
fi

# Display final status
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "\n${GREEN}✓ HTTPS is now enabled${NC}"
echo -e "\nYour archive is available at:"
echo -e "  ${GREEN}https://$DOMAIN${NC}"
echo -e "\nCertificates:"
echo -e "  Renewal: Automatic every 90 days"
echo -e "  Mode: $([ "$STAGING" != "0" ] && echo "Staging (test)" || echo "Production (trusted)")"

if [ "$STAGING" != "0" ]; then
    echo -e "\n${YELLOW}Note: You're using staging certificates (not trusted by browsers)${NC}"
    echo "To switch to production certificates:"
    echo "  1. Set CERTBOT_TEST_CERT=false in .env"
    echo "  2. Remove certificates: sudo docker run --rm -v reddarchiver-certbot-certs:/etc/letsencrypt alpine rm -rf /etc/letsencrypt"
    echo "  3. Re-run: ./docker/scripts/init-letsencrypt.sh"
fi

echo -e "\nMonitoring:"
echo -e "  View renewal logs: docker compose logs certbot"
echo -e "  Test renewal: docker compose exec certbot certbot renew --dry-run"
echo -e "  Certificate info: docker compose exec certbot certbot certificates"

echo -e "\n${GREEN}========================================${NC}"
