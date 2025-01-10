# RevPy

Laravel Reverb Client implemented in Python.

## 📋 Table of Contents
- Features
- Prerequisites
- Installation
- Configuration
- Usage
- Architecture
- API Documentation
- Credits

## ✨ Features
- User authentication
- Reconnection handling
- Heartbeat mechanism
- Channel state persistence
- Example program: Simple message sender in terminal

## 🔧 Prerequisites
- Python 3.11+
- Laravel 10.x
- PHP 8.1+
- Composer

## 📥 Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd websocket-chat
```

2. Install Python dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

3. Install Laravel dependencies:
```bash
composer install
```

4. Copy environment files:
```bash
cp .env.example .env
```

5. Configure your `.env` file with the following values:
```env
REVERB_APP_ID=your_app_id
REVERB_APP_KEY=your_app_key
REVERB_APP_SECRET=your_secret
REVERB_HOST=localhost
REVERB_PORT=8080
REVERB_SCHEME=ws
```

## ⚙️ Configuration

### Laravel Configuration

1. Update your channels.php:
```php
# routes/channels.php
Broadcast::channel('private-chat.{roomName}', function ($user, $id) {
    return true; // Implement your authorization logic
});
```

2. Create an event for handling received messages:
```php
# app/Events/SportChannelMessage.php
<?php

namespace App\Events;

use Illuminate\Broadcasting\Channel;
use Illuminate\Queue\SerializesModels;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Broadcasting\PresenceChannel;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Contracts\Broadcasting\ShouldBroadcastNow;

class SportChannelMessage implements ShouldBroadcastNow
{
    use Dispatchable, InteractsWithSockets, SerializesModels;

    public $message;

    /**
     * Create a new event instance.
     */
    public function __construct($message)
    {
        $this->message = $message;
    }

    /**
     * Get the channels the event should broadcast on.
     *
     * @return array<int, \Illuminate\Broadcasting\Channel>
     */
    public function broadcastOn(): Channel
    {
        return new Channel('private-chat.sports');
    }

    /**
     * The event's broadcast name.
     */
    public function broadcastAs(): string
    {
        return 'client-message';
    }

    /**
     * The data to broadcast.
     */
    public function broadcastWith(): array
    {
        return [
            'message' => $this->message
        ];
    }
}

```

3. Create listener for handling received messages in server (Optional):
```php
# app/Listeners/BroadcastListener.php
<?php

namespace App\Listeners;

use Laravel\Reverb\Events\MessageReceived;

class BroadcastListener
{
    # System events
    private const SYSTEM_EVENTS = [
        'pusher:ping',
        'pusher:pong',
        'pusher:subscribe',
        'pusher:unsubscribe'
    ];

    /**
     * Create the event listener.
     */
    public function __construct()
    {
        //
    }

    /**
     * Handle the event.
     */
    public function handle(MessageReceived $event): void
    {
        // Handle event data here
    }
}
```

### Python Configuration

1. Basic Configuration
```python
options = {
    'key': 'app_key',                # Your Reverb/Pusher app key
    'secret': 'app_secret',          # Your Reverb/Pusher secret key
    'app_key': 'app_key',            # Alternative app key field
    'authEndpoint': 'http://...',    # Authentication endpoint URL
    'debug': False,                  # Enable debug logging
}
```

2. Authentication Options
```python
options = {
    'auth': {
        'headers': {
            'Accept': 'application/json',
            'Authorization': 'Bearer token',
            'Custom-Header': 'value'
        }
    }
}
```

3. Connection Management
```python
options = {
    'reconnect_interval': 2,         # Initial reconnection delay (seconds)
    'max_reconnect_interval': 30,    # Maximum reconnection delay
    'max_retries': 5,               # Maximum connection attempts
    'connect_timeout': 30,          # Connection timeout (seconds)
}
```

4. Heartbeat Settings
```python
options = {
    'pong_timeout': 30,             # Timeout for pong response
    'ping_interval': 120,           # Interval between pings
    'connection_timeout': 305,      # Overall connection timeout
}
```

### Example Full Configuration
```python
options = {
    # Authentication
    'key': 'your_app_key',
    'secret': 'your_app_secret',
    'authEndpoint': 'http://localhost:8000/broadcasting/auth',
    'auth': {
        'headers': {
            'Accept': 'application/json',
            'Authorization': 'Bearer token'
        }
    },

    # Connection
    'reconnect_interval': 2,
    'max_reconnect_interval': 30,
    'max_retries': 5,
    'connect_timeout': 30,

    # Heartbeat
    'pong_timeout': 30,
    'ping_interval': 120,
    'connection_timeout': 305,

    # Debug
    'debug': True
}

connector = WebSocketConnector(uri, options)
```

## Default Values Table

| Option                 | Default | Description                             |
|------------------------|---------|-----------------------------------------|
| reconnect_interval     | 2       | Initial seconds between reconnection attempts |
| max_reconnect_interval | 30      | Maximum seconds between reconnections   |
| max_retries            | 5       | Maximum number of connection attempts   |
| connect_timeout        | 30      | Connection timeout in seconds           |
| pong_timeout           | 30      | Seconds to wait for pong response       |
| ping_interval          | 120     | Seconds between ping messages           |
| connection_timeout     | 305     | Overall connection timeout              |
| debug                  | False   | Enable debug logging                    |

## Example Usage with options

Example of using the Reverb client to connect to the server and send messages:
```python
# main.py
import asyncio
from reverb import Reverb

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
    
    reverb = Reverb(options)
    
    try:
        # Connect to Reverb server
        await reverb.connect()

        # Connect to public channel
        channel = await reverb.channel('chat')

        # Connect to private channel
        channel = await reverb.private('chat.1')

        # Connect to presence channel
        channel = await reverb.presence('chat.1')
        
        # Bind to events
        await channel.listen('client-chat-message', message_handler)
        
        # Send test message
        await channel.send('client-chat-message', {'message': 'Hello World!'})
        
        # Keep connection alive
        while True:
            await asyncio.sleep(1)

            # Disconnect from Reverb server
            await reverb.disconnect()
            
    except KeyboardInterrupt:
        await reverb.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program terminated")
```

## 🚀 Usage

### Starting the Server

1. Start Laravel Reverb server:
```bash
php artisan reverb:start
```

### Running the Client
```bash
python main.py
```

### Running the example Chat Client

1. Run the terminal chat client:
```bash
python chat.py
```

2. Available commands:
- Login with predefined credentials (see `chat.py`)
- Select a chatroom from available options
- Type messages and press Enter to send
- Type 'quit' to exit

## 🏗️ Architecture

### Components

1. `chat.py`

 - Main terminal chat interface
- Handles user authentication
- Manages chatroom selection
- Processes messages

2. `reverb.py`

 - Reverb client implementation
- Manages WebSocket connections
- Handles channel subscriptions
- Implements authentication

3. `channels/__init__.py`

 - Channel management
- Implements WebSocket channel functionality
- Handles event subscriptions
- Manages message broadcasting

4. `connectors/__init__.py`

 - WebSocket connector
- Manages WebSocket connections
- Implements reconnection logic
- Handles heartbeat mechanism

## 📡 API Documentation

### Broadcasting Authentication
> Currently, I don't know how to authenticate the client with the server. 
> For now, use secret key for authentication.

Endpoint: `HOST/broadcasting/auth`
Method: POST
Headers:
```json
{
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Socket-ID": "<socket_id>"
}
```
Body:
```json
{
    "channel_name": "private-chat.1",
    "socket_id": "<socket_id>"
}
```

### Channel Events

1. Client Message:
```python
{
    "event": "client-message",
    "channel": "private-chat.1",
    "data": {
        "message": "Hello World!"
    }
}
```

## ✨ Credits

- Laravel Reverb for WebSocket server
- Python websockets library
- Contributors and maintainers
- PySher for inspiration