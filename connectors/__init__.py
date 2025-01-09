import json
import hmac
import hashlib
import logging
import aiohttp
import websockets
import asyncio
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

        # Add new properties for connection management
        self.needs_reconnect = False
        self.disconnect_called = False
        self.reconnect_interval = options.get('reconnect_interval', 10)
        self.default_reconnect_interval = self.reconnect_interval
        
        # Add properties for ping/pong
        self.pong_received = False
        self.pong_timeout = 30
        self.ping_interval = 120
        self.connection_timeout = 305

    async def connect(self):
        """Establish WebSocket connection"""
        try:
            self.websocket = await websockets.connect(self.uri)
            asyncio.create_task(self._listen_for_messages())
            
            # Wait for connection established
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
    
    async def reconnect(self, reconnect_interval=None):
        """Reconnect to the WebSocket server"""
        if reconnect_interval is None:
            reconnect_interval = self.default_reconnect_interval
            
        self.logger.info(f"Connection: Reconnect in {reconnect_interval}s")
        self.reconnect_interval = reconnect_interval
        
        self.needs_reconnect = True
        if self.websocket:
            await self.websocket.close()
            
        await asyncio.sleep(reconnect_interval)
        await self.connect()

    async def _start_heartbeat(self):
        """Start ping/pong heartbeat"""
        while self.websocket and not self.disconnect_called:
            try:
                await self.send_ping()
                await asyncio.sleep(self.ping_interval)
            except Exception as e:
                self.logger.error(f"Heartbeat error: {str(e)}")
                break

    async def send_ping(self):
        """Send ping message"""
        self.logger.info("Connection: ping to server")
        try:
            await self.send('pusher:ping', '')
            self.pong_received = False
            
            # Wait for pong response
            try:
                async with asyncio.timeout(self.pong_timeout):
                    while not self.pong_received and self.websocket:
                        await asyncio.sleep(1)
                    
                    if not self.pong_received:
                        self.logger.info("Did not receive pong in time. Reconnecting.")
                        await self.reconnect()
            except asyncio.TimeoutError:
                self.logger.info("Pong timeout. Reconnecting.")
                await self.reconnect()
                
        except Exception as e:
            self.logger.error(f"Failed to send ping: {str(e)}")

    async def send_pong(self):
        """Send pong message"""
        self.logger.info("Connection: pong to server") 
        try:
            await self.send('pusher:pong', '')
        except Exception as e:
            self.logger.error(f"Failed to send pong: {str(e)}")

    async def handle_event(self, event, data):
        """Handle incoming events"""
        if event == 'pusher:connection_established':
            self.socket_id = json.loads(data)['socket_id']
            self.state = "connected"
            
            # Start heartbeat
            asyncio.create_task(self._start_heartbeat())
            
        elif event == 'pusher:connection_failed':
            self.state = "failed"
            await self.reconnect()
            
        elif event == 'pusher:error':
            await self._handle_pusher_error(data)
            
        elif event == 'pusher:ping':
            await self.send_pong()
            
        elif event == 'pusher:pong':
            self.logger.info("Connection: pong from server")
            self.pong_received = True

    async def _handle_pusher_error(self, data):
        """Handle Pusher error messages"""
        if 'code' in data:
            try:
                error_code = int(data['code'])
            except:
                error_code = None

            if error_code is not None:
                self.logger.error(f"Connection: Received error {error_code}")

                if 4000 <= error_code <= 4099:
                    # Unrecoverable error
                    self.logger.info("Connection: Error is unrecoverable. Disconnecting")
                    await self.disconnect()
                elif 4100 <= error_code <= 4199:
                    # Reconnect with backoff
                    await self.reconnect()
                elif 4200 <= error_code <= 4299:
                    # Reconnect immediately
                    await self.reconnect(0)
            else:
                self.logger.error("Connection: Unknown error code")
        else:
            self.logger.error("Connection: No error code supplied")

    async def _listen_for_messages(self):
        """Listen for incoming WebSocket messages"""
        try:
            while self.websocket and not self.disconnect_called:
                message = await self.websocket.recv()
                data = json.loads(message)
                
                if 'event' in data:
                    event = data['event']
                    event_data = data.get('data')
                    channel = data.get('channel')
                    
                    # Handle internal events
                    await self.handle_event(event, event_data)
                    
                    # Handle channel events
                    if channel and channel in self.channels:
                        await self.channels[channel].handle_event(event, event_data)
                        
        except websockets.ConnectionClosed:
            if not self.disconnect_called and self.needs_reconnect:
                await self.reconnect()