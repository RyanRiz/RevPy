import asyncio
from reverb import Reverb

async def main():
    options = {}
    echo = Reverb(options)

    channel = await echo.channel('chat')
    await channel.listen('client-message', lambda data: print(f"New message: {data}"))

    await channel.send('client-message', {'message': 'Hello, World!'})

    await channel.run()

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("\nProgram terminated by user")