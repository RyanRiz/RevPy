import os
from dotenv import load_dotenv
from connectors import WebSocketConnector

load_dotenv()

class RevPy:
    def __init__(self, options):
        self.key = os.getenv('REVERB_APP_KEY')
        self.secret = os.getenv('REVERB_APP_SECRET')
        self.app_key = os.getenv('APP_KEY')
        self.options = {
            'key': self.key,
            'secret': self.secret,
            'app_key': self.app_key,
            **options
        }
        
        self.uri = (
            f"{os.getenv('REVERB_SCHEME')}://"
            f"{os.getenv('REVERB_HOST')}:"
            f"{os.getenv('REVERB_PORT')}/app/{self.key}"
        )
        self.connector = WebSocketConnector(self.uri, self.options)

    async def connect(self):
        """Establish connection to Reverb server"""
        return await self.connector.connect()
    
    async def disconnect(self):
        """Close connection to Reverb server"""
        if self.connector:
            await self.connector.disconnect()

    async def channel(self, name):
        """Subscribe to a public channel"""
        return await self.connector.channel(name)

    async def private(self, name):
        """Subscribe to a private channel"""
        return await self.connector.private_channel(name)

    async def presence(self, name):
        """Subscribe to a presence channel"""
        return await self.connector.presence_channel(name)