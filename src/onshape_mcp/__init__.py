"""onshape-mcp. Visual agentic MCP server for Onshape."""

import enum
if not hasattr(enum, "StrEnum"):
    class StrEnum(str, enum.Enum):
        pass
    enum.StrEnum = StrEnum

__version__ = "0.0.1"
