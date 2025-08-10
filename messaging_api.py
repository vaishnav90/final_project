from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime
import json
import asyncio
from pymongo import MongoClient
from bson import ObjectId
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Real-time Messaging API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://vaishnavanand:vannd0108@cluster0.clkkf3n.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
client = MongoClient(MONGO_URI)
db = client['rethread']
messages_collection = db['messages']
users_collection = db['users']

# Data models
class MessageData(BaseModel):
    conversation_id: str
    sender_id: str
    content: str
    message_type: str = "text"

class TypingData(BaseModel):
    conversation_id: str
    user_id: str
    is_typing: bool

class ConnectionManager:
    def __init__(self):
        # Store active connections by conversation_id
        self.conversation_connections: Dict[str, List[WebSocket]] = {}
        # Store user connections for typing indicators
        self.user_connections: Dict[str, WebSocket] = {}
        # Store typing status by conversation
        self.typing_status: Dict[str, Dict[str, bool]] = {}

    async def connect(self, websocket: WebSocket, conversation_id: str, user_id: str):
        await websocket.accept()
        
        # Add to conversation connections
        if conversation_id not in self.conversation_connections:
            self.conversation_connections[conversation_id] = []
        self.conversation_connections[conversation_id].append(websocket)
        
        # Store user connection
        self.user_connections[user_id] = websocket
        
        # Initialize typing status for conversation if not exists
        if conversation_id not in self.typing_status:
            self.typing_status[conversation_id] = {}
        
        print(f"User {user_id} connected to conversation {conversation_id}")

    def disconnect(self, websocket: WebSocket, conversation_id: str, user_id: str):
        # Remove from conversation connections
        if conversation_id in self.conversation_connections:
            if websocket in self.conversation_connections[conversation_id]:
                self.conversation_connections[conversation_id].remove(websocket)
            
            # Clean up empty conversation
            if not self.conversation_connections[conversation_id]:
                del self.conversation_connections[conversation_id]
                if conversation_id in self.typing_status:
                    del self.typing_status[conversation_id]
        
        # Remove user connection
        if user_id in self.user_connections:
            del self.user_connections[user_id]
        
        print(f"User {user_id} disconnected from conversation {conversation_id}")

    async def send_message_to_conversation(self, conversation_id: str, message: dict):
        if conversation_id in self.conversation_connections:
            # Send to all connections in the conversation
            for connection in self.conversation_connections[conversation_id]:
                try:
                    await connection.send_text(json.dumps(message))
                except:
                    # Remove broken connections
                    self.conversation_connections[conversation_id].remove(connection)

    async def send_typing_indicator(self, conversation_id: str, user_id: str, is_typing: bool):
        if conversation_id in self.conversation_connections:
            typing_message = {
                "type": "typing_indicator",
                "conversation_id": conversation_id,
                "user_id": user_id,
                "is_typing": is_typing,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send to all connections in the conversation except the sender
            for connection in self.conversation_connections[conversation_id]:
                try:
                    await connection.send_text(json.dumps(typing_message))
                except:
                    # Remove broken connections
                    self.conversation_connections[conversation_id].remove(connection)

manager = ConnectionManager()

@app.websocket("/ws/{conversation_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str, user_id: str):
    await manager.connect(websocket, conversation_id, user_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "message":
                # Handle new message
                await handle_new_message(conversation_id, user_id, message_data.get("content", ""))
            
            elif message_data.get("type") == "typing":
                # Handle typing indicator
                await handle_typing(conversation_id, user_id, message_data.get("is_typing", False))
            
            elif message_data.get("type") == "typing_stop":
                # Handle stop typing
                await handle_typing(conversation_id, user_id, False)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, conversation_id, user_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket, conversation_id, user_id)

async def handle_new_message(conversation_id: str, sender_id: str, content: str):
    """Handle new message and broadcast to conversation"""
    try:
        # Save message to database
        message_doc = {
            "sender_id": sender_id,
            "content": content,
            "sent_at": datetime.utcnow(),
            "read": False,
            "message_type": "text"
        }
        
        # Update conversation in database
        messages_collection.update_one(
            {"_id": ObjectId(conversation_id)},
            {
                "$push": {"messages": message_doc},
                "$set": {"last_message": datetime.utcnow()}
            }
        )
        
        # Get sender info for display
        sender = users_collection.find_one({"_id": ObjectId(sender_id)})
        sender_name = sender.get("username", "Unknown") if sender else "Unknown"
        
        # Prepare message for broadcasting
        broadcast_message = {
            "type": "new_message",
            "conversation_id": conversation_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "content": content,
            "sent_at": message_doc["sent_at"].isoformat(),
            "message_id": str(ObjectId())  # Generate a temporary ID for the frontend
        }
        
        # Broadcast to all connections in the conversation
        await manager.send_message_to_conversation(conversation_id, broadcast_message)
        
        print(f"Message broadcasted in conversation {conversation_id}")
        
    except Exception as e:
        print(f"Error handling new message: {e}")

async def handle_typing(conversation_id: str, user_id: str, is_typing: bool):
    """Handle typing indicator"""
    try:
        # Update typing status
        if conversation_id not in manager.typing_status:
            manager.typing_status[conversation_id] = {}
        
        manager.typing_status[conversation_id][user_id] = is_typing
        
        # Get user info for display
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        user_name = user.get("username", "Unknown") if user else "Unknown"
        
        # Broadcast typing indicator
        await manager.send_typing_indicator(conversation_id, user_id, is_typing)
        
        print(f"Typing indicator: {user_name} {'is typing' if is_typing else 'stopped typing'} in {conversation_id}")
        
    except Exception as e:
        print(f"Error handling typing indicator: {e}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.get("/conversation/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str):
    """Get messages for a conversation"""
    try:
        conversation = messages_collection.find_one({"_id": ObjectId(conversation_id)})
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {
            "conversation_id": conversation_id,
            "messages": conversation.get("messages", []),
            "participants": conversation.get("participants", [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conversation/{conversation_id}/typing")
async def get_typing_status(conversation_id: str):
    """Get current typing status for a conversation"""
    try:
        if conversation_id in manager.typing_status:
            # Get user names for typing users
            typing_users = []
            for user_id, is_typing in manager.typing_status[conversation_id].items():
                if is_typing:
                    user = users_collection.find_one({"_id": ObjectId(user_id)})
                    if user:
                        typing_users.append({
                            "user_id": user_id,
                            "username": user.get("username", "Unknown")
                        })
            
            return {
                "conversation_id": conversation_id,
                "typing_users": typing_users
            }
        else:
            return {
                "conversation_id": conversation_id,
                "typing_users": []
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
