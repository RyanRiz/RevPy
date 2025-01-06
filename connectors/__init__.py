from channels import WebSocketChannel, WebSocketPrivateChannel, WebSocketPresenceChannel

class WebSocketConnector:
    def __init__(self, uri, options):
        self.uri = uri
        self.options = options
        self.channels = {}

    async def channel(self, name):
        """ Create or retrieve a WebSocket channel."""
        if name not in self.channels:
            self.channels[name] = WebSocketChannel(self.uri, name, self.options)
            await self.channels[name].connect()
        return self.channels[name]

    async def private_channel(self, name):
        """ Create or retrieve a WebSocket private channel."""
        private_name = f'private-{name}'
        if private_name not in self.channels:
            self.channels[private_name] = WebSocketPrivateChannel(self.uri, private_name, self.options)
            await self.channels[private_name].connect()
        return self.channels[private_name]

    async def presence_channel(self, name):
        """ Create or retrieve a WebSocket presence channel."""
        presence_name = f'presence-{name}'
        if presence_name not in self.channels:
            self.channels[presence_name] = WebSocketPresenceChannel(self.uri, presence_name, self.options)
            await self.channels[presence_name].connect()
        return self.channels[presence_name]

    async def leave(self, name):
        """ Leave a channel and its related channels."""
        channels = [name, f'private-{name}', f'presence-{name}']
        for channel_name in channels:
            await self.leave_channel(channel_name)

    async def leave_channel(self, name):
        """ Leave a specific channel."""
        if name in self.channels:
            await self.channels[name].unsubscribe()
            del self.channels[name]

    async def disconnect(self):
        """ Disconnect from all channels."""
        for channel in self.channels.values():
            await channel.unsubscribe()
        self.channels.clear()