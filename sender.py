import asyncio
import json
import websockets
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class MessageSender:
    def __init__(self,):
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.socket_id: Optional[str] = None
        self.running = True

    @property
    def websocket_url(self) -> str:
        return f"{os.getenv('REVERB_SCHEME')}://{os.getenv('REVERB_HOST')}:{os.getenv('REVERB_PORT')}/app/{os.getenv('REVERB_APP_KEY')}"

    async def connect(self) -> None:
        self.websocket = await websockets.connect(self.websocket_url)
        print("Connected to Reverb WebSocket")

    async def subscribe(self) -> None:
        subscribe_data = {
            "event": "pusher:subscribe",
            "data": {"channel": "chat"}
        }
        await self.websocket.send(json.dumps(subscribe_data))
        response = await self.websocket.recv()
        data = json.loads(response)
        if data["event"] == "pusher:connection_established":
            self.socket_id = json.loads(data["data"])["socket_id"]
            print(f"Connected with socket ID: {self.socket_id}")

    async def send_message(self, message: str) -> None:
        if not self.websocket or not self.socket_id:
            print("Not connected")
            return

        message_data = {
            "event": "client-message",
            "data": {
                "channel": "chat",
                "message": message
            }
        }
        await self.websocket.send(json.dumps(message_data))
        await asyncio.sleep(0)  # Yield to the event loop
        print(f"Sent message: {message}")

    async def handle_user_input(self) -> None:
        while self.running:
            try:
                message = input("\nEnter message (or 'quit' to exit): ")
                if message.lower() == 'quit':
                    self.running = False
                    break
                await self.send_message(message)
            except EOFError:
                self.running = False
                break

    async def run(self) -> None:
        try:
            await self.connect()
            await self.subscribe()
            await self.handle_user_input()
        
        except Exception as e:
            print(f"Error: {e}")
        finally:
            self.running = False
            if self.websocket:
                await self.websocket.close()

async def main():
    sender = MessageSender()
    await sender.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram terminated by user")