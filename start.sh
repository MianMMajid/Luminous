#!/bin/bash
set -e

# ── Generate .streamlit/secrets.toml from Railway environment variables ──
# Railway doesn't have the gitignored secrets file, so we create it at runtime.
mkdir -p .streamlit

# Only write auth secrets if Google OAuth is configured
if [ -n "$GOOGLE_CLIENT_ID" ]; then
  cat > .streamlit/secrets.toml <<EOF
[auth]
redirect_uri = "https://${RAILWAY_PUBLIC_DOMAIN}/oauth2callback"
cookie_secret = "${STREAMLIT_COOKIE_SECRET}"
client_id = "${GOOGLE_CLIENT_ID}"
client_secret = "${GOOGLE_CLIENT_SECRET}"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
EOF
  echo "Auth secrets configured for ${RAILWAY_PUBLIC_DOMAIN}"
else
  echo "No GOOGLE_CLIENT_ID set — running without OAuth"
fi

# ── Performance: cache matplotlib fonts ──
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/bioxyc-mpl}"

# ── Start Streamlit ──
exec streamlit run app.py \
  --server.port="${PORT:-8501}" \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --logger.level=warning
