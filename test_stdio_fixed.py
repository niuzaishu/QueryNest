import asyncio
import sys
import os
import traceback
from contextlib import asynccontextmanager

@asynccontextmanager
async def fake_stdio_handler():
    """Simulate the stdio server context manager"""
    print("Entering context manager")
    try:
        # Provide a fake reader and writer
        reader = asyncio.StreamReader()
        writer = asyncio.StreamWriter(sys.stdout.buffer, None, None, None)
        
        yield reader, writer
        
        print("Exiting context manager normally")
    except Exception as e:
        print(f"Error in context manager: {e}")
        traceback.print_exc()
    finally:
        print("In context manager cleanup")

async def main():
    try:
        print("Starting test")
        
        # Test 1: Using context manager with regular exit
        print("\nTest 1: Regular context manager usage")
        async with fake_stdio_handler() as (reader, writer):
            print("Inside context manager")
            await asyncio.sleep(1)  # Simulate some work
            print("Work done")
            # Exit normally
        
        # Test 2: Using context manager with an exception
        print("\nTest 2: Context manager with exception")
        try:
            async with fake_stdio_handler() as (reader, writer):
                print("Inside context manager")
                await asyncio.sleep(1)  # Simulate some work
                raise ValueError("Test exception")
        except ValueError as e:
            print(f"Caught exception: {e}")
        
        print("\nAll tests completed")
    except Exception as e:
        print(f"Unexpected error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    print("Running stdio tests")
    asyncio.run(main())
    print("Tests finished")