import json
import hmac
import hashlib
import logging
import aiohttp
import websockets
from channels import WebSocketChannel

class WebSocketConnector:
    def __init__(self, uri, options):
        self.uri = uri
        self.options = options
        self.websocket = None
        self.socket_id = None
        self.channels = {}
        self.key = options.get('key')
        self.secret = options.get('secret')
        self.app_key = options.get('app_key')
        self.auth_endpoint = options.get('authEndpoint')
        self.auth_headers = options.get('auth', {}).get('headers', {})
        self.logger = logging.getLogger(__name__)

    async def connect(self):
        """Establish WebSocket connection"""
        try:
            self.websocket = await websockets.connect(self.uri)
            message = await self.websocket.recv()
            data = json.loads(message)
            
            if data['event'] == 'pusher:connection_established':
                self.socket_id = json.loads(data['data'])['socket_id']
                return self
            else:
                raise ConnectionError("Failed to establish connection")
        except Exception as e:
            self.logger.error(f"Connection failed: {str(e)}")
            raise

    async def disconnect(self):
        """Close WebSocket connection"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            self.socket_id = None

    async def send(self, event, data, channel=None):
        """Send message through WebSocket"""
        if not self.websocket:
            raise ConnectionError("Not connected")
            
        message = {
            'event': event,
            'data': data
        }
        if channel:
            message['channel'] = channel
            
        await self.websocket.send(json.dumps(message))

    async def _generate_auth_token(self, channel_name):
        """Generate authentication token"""
        if not self.socket_id:
            raise ValueError("No socket_id available")

        if self.secret:
            # For local testing with secret
            channel_data = json.dumps({
                'key': self.app_key,
            })
            to_sign = f"{self.socket_id}:{channel_name}:{channel_data}" if channel_name.startswith('presence-') else f"{self.socket_id}:{channel_name}"
            signature = hmac.new(
                self.secret.encode(),
                to_sign.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if channel_name.startswith('presence-'):
                return {
                    'auth': f"{self.key}:{signature}",
                    'channel_data': channel_data
                }
            return f"{self.key}:{signature}"
            
        elif self.auth_endpoint:
            async with aiohttp.ClientSession() as session:
                payload = {
                    'socket_id': self.socket_id,
                    'channel_name': channel_name
                }
                
                async with session.post(
                    self.auth_endpoint,
                    json=payload,
                    headers=self.auth_headers
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"Auth failed: {await response.text()}")
                    return await response.json()
        else:
            raise ValueError("Either secret or auth_endpoint required")

    async def channel(self, name):
        """Create or get public channel"""
        if name not in self.channels:
            self.channels[name] = WebSocketChannel(self, name)
            await self.channels[name].subscribe()
        return self.channels[name]

    async def private_channel(self, name):
        """Create or get private channel"""
        private_name = f'private-{name}'
        if private_name not in self.channels:
            auth = await self._generate_auth_token(private_name)
            self.channels[private_name] = WebSocketChannel(
                self,
                private_name,
                auth=auth
            )
            await self.channels[private_name].subscribe()
        return self.channels[private_name]
    
    async def presence_channel(self, name):
        """Create or get presence channel"""
        presence_name = f'presence-{name}'
        if presence_name not in self.channels:
            auth = await self._generate_auth_token(presence_name)
            self.channels[presence_name] = WebSocketChannel(
                self,
                presence_name,
                auth=auth
            )
            await self.channels[presence_name].subscribe()
        return self.channels[presence_name]