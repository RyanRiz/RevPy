import json
from websockets import connect

class WebSocketChannel:

    def __init__(self, uri, name, options):
        self.uri = uri
        self.name = name
        self.options = options
        self.websocket = None
        self.subscribed = False
        self.listeners = {}

    async def connect(self):
        """ Establish a WebSocket connection and subscribe to the channel."""
        self.websocket = await connect(self.uri, ping_timeout=None)
        await self.subscribe()

    async def subscribe(self):
        """ Subscribe to the channel if not already subscribed."""
        if not self.subscribed:
            await self.websocket.send(json.dumps({
                'event': 'pusher:subscribe',
                'data': {
                    'channel': self.name
                }
            }))
            self.subscribed = True

    async def unsubscribe(self):
        """ Unsubscribe from the channel and close the WebSocket connection."""
        if self.subscribed:
            await self.websocket.send(json.dumps({
                'event': 'pusher:unsubscribe',
                'data': {
                    'channel': self.name
                }
            }))
            self.subscribed = False
            await self.websocket.close()

    async def send(self, event, data):
        """ Send a message to the channel."""
        if self.subscribed:
            structered_data = {'channel': self.name, **data}
            await self.websocket.send(json.dumps({
                'event': event,
                'data': structered_data
            }))

    async def listen(self, event, callback):
        """ Start listening for events on the channel."""
        self.listeners[event] = callback

    async def stop_listening(self, event):
        """ Stop listening for a specific event."""
        if event in self.listeners:
            del self.listeners[event]

    async def handle_message(self, message):
        """ Handle incoming messages and trigger the appropriate listener."""
        data = json.loads(message)
        if 'event' in data and data['event'] in self.listeners:
            self.listeners[data['event']](data.get('data'))

    async def run(self):
        """ Run the channel to keep listening for messages."""
        while self.subscribed:
            message = await self.websocket.recv()
            await self.handle_message(message)


class WebSocketPrivateChannel(WebSocketChannel):
    async def whisper(self, event_name, data):
        """ Send a whisper to the private channel."""
        structered_data = {'channel': self.name, **data}
        await self.websocket.send(json.dumps({
            'event': f'client-{event_name}',
            'data': structered_data
        }))


class WebSocketPresenceChannel(WebSocketPrivateChannel):
    async def here(self, callback):
        """ Get the current members of the presence channel."""
        await self.listen('pusher:subscription_succeeded', lambda data: callback(data['members']))

    async def joining(self, callback):
        """ Listen for new members joining the presence channel."""
        await self.listen('pusher:member_added', lambda data: callback(data['info']))

    async def leaving(self, callback):
        """ Listen for members leaving the presence channel."""
        await self.listen('pusher:member_removed', lambda data: callback(data['info']))