import json
import hmac
import hashlib
import logging
import os
import random
import aiohttp
import websockets
import asyncio
from channels import WebSocketChannel

def setup_logging(debug=False):
    """Configure logging for the WebSocket connector"""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Remove existing handlers
    logger.handlers = []

    # Create handlers
    console_handler = logging.StreamHandler()
    file_handler = logging.FileHandler('websocket.log')
    
    # Set levels based on debug flag
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Create formatters and add it to handlers
    log_format = logging.Formatter('\n%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(log_format)
    file_handler.setFormatter(log_format)
    
    # Add handlers to the logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

class WebSocketConnector:
    def __init__(self, uri, options):
        # Initialization
        self.uri = uri
        self.options = options
        self.websocket = None
        self.socket_id = None
        self.channels = {}
        self.channel_states = {}
        self.key = options.get('key')
        self.secret = options.get('secret')
        self.app_key = options.get('app_key')
        self.auth_endpoint = options.get('authEndpoint')
        self.auth_headers = options.get('auth', {}).get('headers', {})

        # Debug configuration
        self.debug = options.get('debug', False)
        self.logger = setup_logging(self.debug)

        # Connection management
        self.state = "disconnected"
        self.needs_reconnect = False
        self.disconnect_called = False
        self.reconnect_interval = options.get('reconnect_interval', 2)
        self.default_reconnect_interval = self.reconnect_interval
        self.max_reconnect_interval = options.get('max_reconnect_interval', 30)
        self.max_retries = options.get('max_retries', 5)
        self.retry_count = 0
        self.connect_timeout = options.get('connect_timeout', 30)
        
        # Heartbeat settings
        self.pong_received = False
        self.pong_timeout = 30
        self.ping_interval = 120
        self.connection_timeout = 305

        # Connection status
        self.connection_ready = False
        self.connection_established = asyncio.Event()

        # Background tasks
        self.listener_task = None
        self.listener_active = False
        self.listener_lock = asyncio.Lock()

        # Enhanced task management
        self.tasks = set()
        self.active_listener = None
        self.listener_state = asyncio.Event()
        
        # Enhanced queue management
        self.message_queue = asyncio.Queue()
        self.processing = False
        self.messages_in_flight = 0
        self.queue_lock = asyncio.Lock()

    async def _process_messages(self):
        """Process messages from queue with enhanced error handling"""
        self.processing = True
        
        try:
            while self.processing:
                try:
                    # Get message with timeout to allow clean shutdown
                    message = await asyncio.wait_for(
                        self.message_queue.get(),
                        timeout=1.0
                    )
                    
                    if message is None:  # Shutdown signal
                        break
                        
                    try:
                        data = json.loads(message)
                        if 'event' in data:
                            event = data['event']
                            event_data = data.get('data')
                            channel = data.get('channel')

                            if self.debug:
                                self.logger.debug(f"Processing event: {event}")
                                self.logger.debug(f"Channel: {channel}")
                                self.logger.debug(f"Data: {event_data}")
                            
                            # Handle internal events
                            await self.handle_event(event, event_data)
                            
                            # Handle channel events
                            if channel and channel in self.channels:
                                await self.channels[channel].handle_event(event, event_data)
                                
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Invalid message format: {str(e)}")
                    except Exception as e:
                        self.logger.error(f"Message processing error: {str(e)}")
                    finally:
                        # Only mark task as done if we actually got a message
                        self.message_queue.task_done()
                        
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"Queue processing error: {str(e)}")
                    await asyncio.sleep(1)  # Prevent tight error loop
                    
        except Exception as e:
            self.logger.error(f"Message processor error: {str(e)}")
        finally:
            self.processing = False

    async def _start_message_listener(self):
        """Start message listener with queue management"""
        async with self.listener_lock:
            # Cancel existing tasks
            if self.active_listener and not self.active_listener.done():
                self.active_listener.cancel()
                try:
                    await self.active_listener
                except asyncio.CancelledError:
                    pass
                    
            # Clear queue state
            while not self.message_queue.empty():
                try:
                    self.message_queue.get_nowait()
                    self.message_queue.task_done()
                except (asyncio.QueueEmpty, ValueError):
                    pass
                    
            # Start new processor
            processor = asyncio.create_task(self._process_messages())
            self.tasks.add(processor)
            
            # Start new listener
            self.listener_state.set()
            self.active_listener = asyncio.create_task(self._listen_for_messages())
            self.tasks.add(self.active_listener)

    async def _wait_for_connection(self):
        """Wait for connection to be ready"""
        if not self.connection_ready:
            await self.connection_established.wait()
        return self.socket_id is not None

    async def connect(self):
        """Establish WebSocket connection with simplified validation"""
        self.retry_count = 0
        self.reconnect_interval = self.default_reconnect_interval
        self.connection_established.clear()

        while self.retry_count < self.max_retries:
            try:
                self.state = "connecting"
                if self.debug:
                    self.logger.debug(f"Connecting to {self.uri}")
                    self.logger.debug(f"Connection attempt {self.retry_count + 1}/{self.max_retries}")
                
                # Add connection timeout (compatible with Python <3.11)
                self.websocket = await asyncio.wait_for(
                    websockets.connect(
                        self.uri,
                        close_timeout=5,
                        ping_interval=None
                    ),
                    timeout=self.connect_timeout
                )
                # Wait for connection established message
                message = await self.websocket.recv()
                if self.debug:
                    self.logger.debug(f"Received message: {message}")
                data = json.loads(message)
                if data['event'] == 'pusher:connection_established':
                    self.socket_id = json.loads(data['data'])['socket_id']
                    self.state = "connected"
                    self.connection_ready = True
                    self.connection_established.set()
                    if self.debug:
                        self.logger.debug(f"Connected successfully with socket_id: {self.socket_id}")
                    else:
                        print("Connected successfully")
                    # Start new message listener
                    await self._start_message_listener()
                    return self
                raise ConnectionError("Unexpected connection response")
                    
            except asyncio.TimeoutError:
                self.logger.error(f"Connection attempt timed out after {self.connect_timeout}s")
                await self._handle_connection_refused()
                
            except ConnectionRefusedError as e:
                self.logger.error(f"Connection refused: {str(e)}")
                await self._handle_connection_refused()
                
            except Exception as e:
                if self.debug:
                    self.logger.debug(f"Connection error details: {str(e)}")
                self.logger.error(f"Connection failed: {type(e).__name__}")
                await self._handle_connection_refused()

        self.logger.error("Connection failed after max retries")
        self.state = "failed"
        os._exit(1)

    async def _handle_connection_refused(self):
        """Handle connection refused with exponential backoff and jitter"""
        self.retry_count += 1
        
        # Calculate backoff with jitter
        jitter = random.uniform(0, 0.1) * self.reconnect_interval
        backoff = min(
            (self.reconnect_interval * 2) + jitter,
            self.max_reconnect_interval
        )
        
        self.logger.info(
            f"Connection refused. Retrying in {backoff:.1f} seconds... "
            f"(Attempt {self.retry_count}/{self.max_retries})"
        )
        
        # Clean up existing connection if any
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            
        self.reconnect_interval = backoff
        await asyncio.sleep(backoff)

    async def reconnect(self, reconnect_interval=None):
        """Reconnect with queue cleanup"""
        if self.state == "reconnecting":
            return
            
        self.state = "reconnecting"
        self.processing = False
        self.listener_state.clear()
        
        # Clean up queue
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
                self.message_queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                pass
        
        # Store channel states
        stored_channels = {
            name: self._serialize_channel(name, channel)
            for name, channel in self.channels.items()
        }
        
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            
        await asyncio.sleep(reconnect_interval or self.default_reconnect_interval)
        
        try:
            await self.connect()
            if self.connection_ready:
                await self._restore_channels(stored_channels)
                self.logger.info("Successfully reconnected and restored channels")
                await self._start_message_listener()
        except Exception as e:
            self.logger.error(f"Reconnection failed: {str(e)}")

    async def disconnect(self):
        """Enhanced disconnect with listener cleanup"""
        self.disconnect_called = True
        self.listener_active = False
        
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
            self.listener_task = None
            
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            self.socket_id = None

    def _serialize_channel(self, channel_name, channel):
        """Convert channel to serializable format"""
        return {
            'name': channel_name,
            'auth': channel.auth,
            'subscribed': channel.subscribed
        }
        
    async def _restore_channels(self, stored_channels):
        """Restore channels after reconnection"""
        for channel_name, state in stored_channels.items():
            if channel_name.startswith(('private-', 'presence-')):
                auth = await self._generate_auth_token(channel_name)
                channel = WebSocketChannel(self, channel_name, auth)
            else:
                channel = WebSocketChannel(self, channel_name)
                
            self.channels[channel_name] = channel
            if state['subscribed']:
                await channel.subscribe()

    async def send(self, event, data, channel=None):
        """Send message through WebSocket with retry and reconnect"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                if not self.websocket or not self.connection_ready:
                    await self.connect()
                
                # Create serializable message
                message = {
                    'event': event,
                    'data': data
                }
                if channel:
                    message['channel'] = channel if isinstance(channel, str) else channel.name
                
                await self.websocket.send(json.dumps(message))
                return
                
            except websockets.ConnectionClosedError:
                retry_count += 1
                self.logger.info(f"Connection closed. Attempting reconnect ({retry_count}/{max_retries})")
                
                # Store channel states before reconnection
                self.channel_states = {
                    name: self._serialize_channel(name, chan) 
                    for name, chan in self.channels.items()
                }
                self.channels = {}
                
                # Reset connection state
                self.connection_ready = False
                self.connection_established.clear()
                self.websocket = None
                
                if retry_count < max_retries:
                    # Attempt reconnection with backoff
                    await asyncio.sleep(retry_count * 2)
                    await self.connect()
                    
                    # Restore channels
                    await self._restore_channels(self.channel_states)
                    continue
                    
            except TypeError as e:
                # Handle JSON serialization errors
                if "not JSON serializable" in str(e):
                    self.logger.error(f"Serialization error: {str(e)}")
                    message['channel'] = str(channel)
                    retry_count += 1
                    continue
                raise
                
            except Exception as e:
                self.logger.error(f"Send error: {str(e)}")
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(retry_count)
                    continue
                raise
                
        raise ConnectionError("Failed to send message after maximum retries")

    async def _generate_auth_token(self, channel_name):
        """Generate authentication token"""
        if not await self._wait_for_connection():
            await self.connect()
            if not self.socket_id:
                raise ValueError("Could not establish connection")

        if self.secret:
            # Auth with secret
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
            # Auth with endpoint
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

    async def private_channel(self, name):
        """Subscribe to private channel with connection validation"""
        if not await self._wait_for_connection():
            await self.connect()
        
        private_name = f"private-{name}"
        auth = await self._generate_auth_token(private_name)
        channel = WebSocketChannel(self, private_name, auth)
        self.channels[private_name] = channel
        await channel.subscribe()
        return channel

    async def presence_channel(self, name):
        """Subscribe to presence channel with connection validation"""
        if not await self._wait_for_connection():
            await self.connect()
            
        presence_name = f"presence-{name}"
        auth = await self._generate_auth_token(presence_name)
        channel = WebSocketChannel(self, presence_name, auth)
        self.channels[presence_name] = channel
        await channel.subscribe()
        return channel
    
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
        if self.debug:
            self.logger.info("Connection: ping to server")
        try:
            await self.send('pusher:ping', '')
            self.pong_received = False
            # Wait for pong response
            try:
                await asyncio.wait_for(
                    self._wait_for_pong(),
                    timeout=self.pong_timeout
                )
            except asyncio.TimeoutError:
                self.logger.info("Pong timeout. Reconnecting.")
                await self.reconnect()
        except Exception as e:
            self.logger.error(f"Failed to send ping: {str(e)}")

    async def _wait_for_pong(self):
        while not self.pong_received and self.websocket:
            await asyncio.sleep(1)
        if not self.pong_received:
            self.logger.info("Did not receive pong in time. Reconnecting.")
            await self.reconnect()

    async def send_pong(self):
        """Send pong message"""
        if self.debug:
            self.logger.info("Connection: pong to server") 
        try:
            await self.send('pusher:pong', '')
        except Exception as e:
            if self.debug:
                self.logger.error(f"Failed to send pong: {str(e)}")

    async def handle_event(self, event, data):
        """Handle incoming events"""
        if event == 'pusher:connection_established':
            self.socket_id = json.loads(data)['socket_id']
            self.state = "connected"
            
            # Start heartbeat
            # asyncio.create_task(self._start_heartbeat())
            
        elif event == 'pusher:connection_failed':
            self.state = "failed"
            await self.reconnect()
            
        elif event == 'pusher:error':
            await self._handle_pusher_error(data)
            
        elif event == 'pusher:ping':
            await self.send_pong()
            
        elif event == 'pusher:pong':
            if self.debug:
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
        """Enhanced message listener with queue"""
        try:
            while self.listener_state.is_set() and self.websocket:
                try:
                    message = await self.websocket.recv()
                    if self.debug:
                        self.logger.debug(f"Received: {message}")
                    await self.message_queue.put(message)
                    
                except websockets.ConnectionClosed:
                    if self.debug:
                        self.logger.debug("WebSocket connection closed")
                    if not self.disconnect_called:
                        await self.reconnect()
                    break
                    
        except Exception as e:
            self.logger.error(f"Listener error: {str(e)}")
            if not self.disconnect_called:
                await self.reconnect()
        finally:
            self.listener_state.clear()