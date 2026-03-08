import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TAMARIND_API_KEY = os.getenv("TAMARIND_API_KEY", "")
BIORENDER_TOKEN = os.getenv("BIORENDER_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

TAMARIND_BASE_URL = "https://app.tamarind.bio/api"
PUBMED_MCP_URL = "https://pubmed.mcp.claude.com/mcp"
OPEN_TARGETS_MCP_URL = "https://mcp.platform.opentargets.org/mcp"
BIORENDER_MCP_URL = "https://mcp.services.biorender.com/mcp"
WILEY_MCP_URL = "https://mcp.wiley.com/mcp"

CLAUDE_MODEL = "claude-opus-4-6"
CLAUDE_FAST_MODEL = "claude-sonnet-4-20250514"
MCP_BETA_HEADER = "mcp-client-2025-11-20"
