"""Allow running as: python -m psu_mcp"""

from psu_mcp.server import main

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
