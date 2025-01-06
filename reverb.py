import os
from dotenv import load_dotenv
from connectors import WebSocketConnector

load_dotenv()

class Reverb:
    def __init__(self, options):
        self.uri = f"{os.getenv('REVERB_SCHEME')}://{os.getenv('REVERB_HOST')}:{os.getenv('REVERB_PORT')}/app/{os.getenv('REVERB_APP_KEY')}"
        self.options = options
        self.connector = WebSocketConnector(self.uri, options)

    async def channel(self, name):
        return await self.connector.channel(name)

    async def private(self, name):
        return await self.connector.private_channel(name)

    async def presence(self, name):
        return await self.connector.presence_channel(name)

    async def leave(self, name):
        await self.connector.leave(name)

    async def leave_channel(self, name):
        await self.connector.leave_channel(name)

    async def disconnect(self):
        await self.connector.disconnect()