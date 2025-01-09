from collections import defaultdict

class WebSocketChannel:
    def __init__(self, connector, name, auth=None):
        self.connector = connector
        self.name = name
        self.auth = auth
        self.event_handlers = defaultdict(list)
        self.subscribed = False

    async def subscribe(self):
        """Subscribe to channel"""
        if not self.subscribed:
            data = {'channel': self.name}
            if isinstance(self.auth, dict):
                data.update(self.auth)
            elif self.auth:
                data['auth'] = self.auth
                
            await self.connector.send('pusher:subscribe', data)
            self.subscribed = True

    async def send(self, event, data):
        """Send message on channel"""
        event = f'client-{event}'
        await self.connector.send(event, data, self.name)

    async def listen(self, event, callback):
        """Bind event handler"""
        self.event_handlers[event].append(callback)

    async def handle_event(self, event, data):
        """Handle incoming event"""
        for handler in self.event_handlers[event]:
            await handler(data)