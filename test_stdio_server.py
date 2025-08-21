import asyncio
import structlog
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(ensure_ascii=False)
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("test_stdio_server")

async def main():
    # Create a server
    server = Server("test_server")
    
    # Register a simple tool
    @server.list_tools()
    async def handle_list_tools():
        logger.info("Listing tools")
        return [Tool(
            name="echo",
            description="Echo back the input",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to echo"
                    }
                },
                "required": ["message"]
            }
        )]
    
    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict):
        logger.info("Tool called", tool=name, args=arguments)
        if name == "echo":
            message = arguments.get("message", "")
            return [TextContent(type="text", text=f"Echo: {message}")]
        return []

    try:
        logger.info("Starting stdio server")
        print("Server starting, waiting for stdin input...")
        
        async with stdio_server() as (read_stream, write_stream):
            logger.info("Stdio server opened")
            print("Stdio server opened, running server...")
            
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="test_server",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    )
                )
            )
            
        logger.info("Server completed")
    except Exception as e:
        logger.error("Server error", error=str(e))
        raise

if __name__ == "__main__":
    print("Starting asyncio event loop...")
    asyncio.run(main())
    print("Event loop finished")