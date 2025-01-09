import getpass
import asyncio
from termcolor import colored
from reverb import Reverb
from dotenv import load_dotenv
from datetime import datetime
import json

load_dotenv()

class TerminalChat:
    def __init__(self):
        self.reverb = None
        self.channel = None
        self.chatroom = None
        self.user = None
        self.running = True
        self.users = {
            "samuel": "abc",
            "daniel": "abc",
            "tobi": "abc",
            "sarah": "abc"
        }
        self.chatrooms = ["sports", "general", "education", "health", "technology"]
        self.debug = False
        self.last_message_time = None

    def clear_line(self):
        """Clear current line and move cursor up"""
        print('\033[2K\033[1G', end='')

    async def main(self):
        """Entry point of the application"""
        self.login()
        self.selectChatroom()
        await self.initReverb()
        await self.messageLoop()

    def login(self):
        """Handle user authentication"""
        username = input("Please enter your username: ")
        password = getpass.getpass(f"Please enter {username}'s Password: ")
        
        if username in self.users:
            if self.users[username] == password:
                self.user = username
            else:
                print(colored("Your password is incorrect", "red"))
                self.login()
        else:
            print(colored("Your username is incorrect", "red"))
            self.login()

    def selectChatroom(self):
        """Select a chatroom to join"""
        print(colored(f"Info! Available chatrooms are {str(self.chatrooms)}", "blue"))
        chatroom = input(colored("Please select a chatroom: ", "green"))
        
        if chatroom in self.chatrooms:
            self.chatroom = chatroom
        else:
            print(colored("No such chatroom in our list", "red"))
            self.selectChatroom()

    def print_message(self, sender: str, message: str, color: str = "white", show_timestamp: bool = True) -> None:
        """Print formatted chat message"""
        self.clear_line()
        timestamp = f"[{datetime.now().strftime('%H:%M:%S')}] " if show_timestamp else ""
        print(colored(f"\n{timestamp}{sender}: {message}", color))
        print(colored(f"{self.user}: ", "green"), end='', flush=True)

    async def message_handler(self, data):
        """Handle incoming messages"""
        try:
            if not isinstance(data, dict):
                data = json.loads(data) if isinstance(data, str) else {"message": str(data)}
            
            if 'user' in data and 'message' in data:
                sender = data['user']
                message = data['message']
                
                # Show all messages including own messages
                color = "white"
                if sender != self.user:
                    self.print_message(sender, message, color=color)
                
                if self.debug:
                    print(f"\nDebug - Received message: {data}")
                    
        except Exception as e:
            if self.debug:
                print(f"\nDebug - Message handler error: {str(e)}")

    async def initReverb(self):
        """Initialize Reverb connection"""
        options = {
            'debug': self.debug,  # Enable WebSocket debug logging
            'authEndpoint': 'http://localhost:8000/broadcasting/auth',
            'auth': {
                'headers': {
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {self.user}-token'
                }
            }
        }
        
        self.reverb = Reverb(options)
        await self.reverb.connect()
        
        # Subscribe to private channel for the chatroom
        channel_name = f"chat.{self.chatroom}"
        self.channel = await self.reverb.private(channel_name)
        
        if self.debug:
            print(f"Debug - Subscribed to channel: {channel_name}")
            
        await self.channel.listen('client-chat-message', self.message_handler)

    async def messageLoop(self):
        """Main message loop"""
        try:
            while self.running:
                message = await self.get_async_input()
                if message.strip():
                    if message.lower() == 'quit':
                        self.running = False
                        break
                    
                    # Create message payload
                    msg_data = {
                        'user': self.user,
                        'message': message
                    }
                    
                    # Send message and call handler directly for local echo
                    await self.channel.send('chat-message', msg_data)
                    await self.message_handler(msg_data)
                    
        except KeyboardInterrupt:
            self.running = False
        finally:
            if self.reverb:
                await self.reverb.disconnect()
                print(colored("\n--- Disconnected from chat ---", "yellow"))

    async def get_async_input(self):
        """Get user input asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: input(colored(f"{self.user}: ", "green")))

if __name__ == "__main__":
    chat = TerminalChat()
    try:
        asyncio.run(chat.main())
    except KeyboardInterrupt:
        print("\nChat terminated by user")