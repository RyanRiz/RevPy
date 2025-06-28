# main.py
import asyncio
from revpy import RevPy

async def message_handler(data):
    print(f"Received message: {data}")

async def main():
    """
    Change the authEndpoint to the URL of your authentication endpoint
    if you want to use authentication with your Reverb server instead of using secret tokens.
    """
    options = {
        'authEndpoint': 'http://localhost:8000/broadcasting/auth',
        'auth': {
            'headers': {
                'Accept': 'application/json',
                'Authorization': 'Bearer my-secret-token'
            }
        }
    }
    
    reverb = RevPy(options)
    
    try:
        # Connect to Reverb server
        await reverb.connect()

        # Connect to private channel
        channel = await reverb.presence('chat.1')
        
        # Bind to events
        await channel.listen('client-chat-message', message_handler)
        
        # Send test message
        await channel.send('client-chat-message', {'message': 'Hello World!'})
        
        # Keep connection alive
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        await reverb.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program terminated")