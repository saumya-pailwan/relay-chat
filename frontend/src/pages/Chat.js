import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Send, LogOut, Plus, Users, Search, UserPlus, Paperclip } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const WS_URL = BACKEND_URL.replace("https://", "wss://").replace("http://", "ws://");

export default function Chat({ token, user, onLogout }) {
  const [rooms, setRooms] = useState([]);
  const [activeRoom, setActiveRoom] = useState(null);
  const [messages, setMessages] = useState([]);
  const [messageInput, setMessageInput] = useState("");
  const [ws, setWs] = useState(null);
  const [connected, setConnected] = useState(false);
  const [showCreateRoom, setShowCreateRoom] = useState(false);
  const [newRoomName, setNewRoomName] = useState("");
  const [onlineUsers, setOnlineUsers] = useState({});
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [showAddMember, setShowAddMember] = useState(false);
  const [memberEmail, setMemberEmail] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [oldestTimestamp, setOldestTimestamp] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const fileInputRef = useRef(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    fetchRooms();
  }, []);

  useEffect(() => {
    if (!token) return;

    const websocket = new WebSocket(`${WS_URL}/api/ws?token=${token}`);

    websocket.onopen = () => {
      setConnected(true);
      setWs(websocket);
    };

    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "chat_message") {
        setMessages((prev) => {
          if (prev.some(msg => msg.id === data.id)) return prev;

          const confirmed = {
            id: data.id,
            room_id: data.room_id,
            user_id: data.user_id,
            username: data.username,
            content: data.content,
            timestamp: data.timestamp,
            attachments: data.attachments || []
          };

          if (data.user_id === user?.id) {
            const tempIdx = prev.findLastIndex(
              m => m.id.startsWith("temp-") && m.room_id === data.room_id && m.content === data.content
            );
            if (tempIdx !== -1) {
              const updated = [...prev];
              updated[tempIdx] = confirmed;
              return updated;
            }
          }

          return [...prev, confirmed];
        });
      } else if (data.type === "presence_update") {
        setOnlineUsers(data.online_users || {});
      } else if (data.type === "user_joined") {
        toast.info(data.message);
      } else if (data.type === "system") {
        toast.info(data.message);
      } else if (data.type === "error") {
        toast.error(data.message);
      }
    };

    websocket.onerror = (error) => {
      toast.error("Connection error");
    };

    websocket.onclose = () => {
      setConnected(false);
    };

    return () => {
      if (websocket.readyState === WebSocket.OPEN) {
        websocket.close();
      }
    };
  }, [token]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    const searchTimeout = setTimeout(async () => {
      if (searchQuery.length >= 2) {
        try {
          const response = await axios.get(`${API}/users/search?q=${searchQuery}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          setSearchResults(response.data);
        } catch (error) {
          console.error(error);
        }
      } else {
        setSearchResults([]);
      }
    }, 300);

    return () => clearTimeout(searchTimeout);
  }, [searchQuery, token]);

  const fetchRooms = async () => {
    try {
      const response = await axios.get(`${API}/rooms`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setRooms(response.data);
      if (response.data.length > 0 && !activeRoom) {
        selectRoom(response.data[0]);
      }
    } catch (error) {
      toast.error("Failed to load rooms");
    }
  };

  const selectRoom = async (room) => {
    setActiveRoom(room);
    setMessages([]);
    setOldestTimestamp(null);
    setHasMore(false);

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: "join_room", room_id: room.id }));
    }

    try {
      const response = await axios.get(`${API}/rooms/${room.id}/messages`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = response.data;
      setMessages(data);
      if (data.length > 0) {
        setOldestTimestamp(data[0].timestamp);
        setHasMore(data.length === 50);
      }
    } catch (error) {
      toast.error("Failed to load messages");
    }
  };

  const loadOlderMessages = async () => {
    if (!activeRoom || !oldestTimestamp || loadingMore) return;
    setLoadingMore(true);
    try {
      const response = await axios.get(
        `${API}/rooms/${activeRoom.id}/messages?before=${encodeURIComponent(oldestTimestamp)}&limit=50`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const older = response.data;
      if (older.length > 0) {
        setMessages((prev) => [...older, ...prev]);
        setOldestTimestamp(older[0].timestamp);
        setHasMore(older.length === 50);
      } else {
        setHasMore(false);
      }
    } catch (error) {
      toast.error("Failed to load older messages");
    } finally {
      setLoadingMore(false);
    }
  };

  const createRoom = async (e) => {
    e.preventDefault();
    if (!newRoomName.trim()) return;

    try {
      const response = await axios.post(
        `${API}/rooms`,
        { name: newRoomName, type: "group", members: [] },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success("Room created!");
      setNewRoomName("");
      setShowCreateRoom(false);
      await fetchRooms();
      selectRoom(response.data);
    } catch (error) {
      toast.error("Failed to create room");
    }
  };

  const startDirectMessage = async (identifier) => {
    try {
      const response = await axios.post(
        `${API}/rooms/direct`,
        { identifier: identifier },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success("Direct message started!");
      await fetchRooms();
      selectRoom(response.data);
      setSearchQuery("");
      setSearchResults([]);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to start DM");
    }
  };

  const addMemberToRoom = async (e) => {
    e.preventDefault();
    if (!memberEmail.trim() || !activeRoom) return;

    try {
      const response = await axios.post(
        `${API}/rooms/${activeRoom.id}/members/add`,
        { user_email: memberEmail },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(response.data.message);
      setMemberEmail("");
      setShowAddMember(false);
      await fetchRooms();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to add member");
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await axios.post(`${API}/upload`, formData, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "multipart/form-data",
        },
      });

      const { url, filename } = response.data;

      const optimisticMessage = {
        id: `temp-${Date.now()}`,
        room_id: activeRoom.id,
        user_id: user?.id,
        username: user?.username,
        content: `Sent a file: ${filename}`,
        timestamp: new Date().toISOString(),
        attachments: [url]
      };
      setMessages((prev) => [...prev, optimisticMessage]);

      ws.send(
        JSON.stringify({
          action: "send_message",
          room_id: activeRoom.id,
          content: `Sent a file: ${filename}`,
          attachments: [url]
        })
      );
    } catch (error) {
      toast.error("Failed to upload file");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const sendMessage = (e) => {
    e.preventDefault();
    if (!messageInput.trim() || !activeRoom || !ws) {
      return;
    }

    const optimisticMessage = {
      id: `temp-${Date.now()}`,
      room_id: activeRoom.id,
      user_id: user?.id,
      username: user?.username,
      content: messageInput,
      timestamp: new Date().toISOString(),
      attachments: []
    };
    setMessages((prev) => [...prev, optimisticMessage]);

    ws.send(
      JSON.stringify({
        action: "send_message",
        room_id: activeRoom.id,
        content: messageInput,
      })
    );
    setMessageInput("");
  };

  const filteredRooms = rooms.filter(room =>
    room.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="chat-container">
      <div className="chat-sidebar">
        <div className="sidebar-header">
          <div className="sidebar-title">
            <Users size={20} />
            <span>Chats</span>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowCreateRoom(!showCreateRoom)}
              data-testid="create-room-button"
              title="Create room"
            >
              <Plus size={18} />
            </Button>
          </div>
        </div>

        <div className="search-container">
          <div className="search-input-wrapper">
            <Search size={16} className="search-icon" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search users or rooms..."
              className="search-input"
              data-testid="search-input"
            />
          </div>
          {searchResults.length > 0 && (
            <div className="search-results">
              {searchResults.map((result) => (
                <div
                  key={result.id}
                  className="search-result-item"
                  onClick={() => startDirectMessage(result.email)}
                  data-testid={`search-result-${result.id}`}
                >
                  <div className="user-avatar-small">
                    {result.username?.[0]?.toUpperCase()}
                  </div>
                  <div>
                    <div className="result-username">{result.username}</div>
                    <div className="result-email">{result.email}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
          {searchQuery && searchResults.length === 0 && (
            <div className="search-results">
              <div
                className="search-result-item"
                onClick={() => startDirectMessage(searchQuery)}
              >
                <div className="user-avatar-small">?</div>
                <div>
                  <div className="result-username">Chat with "{searchQuery}"</div>
                  <div className="result-email">Click to start DM</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {showCreateRoom && (
          <form onSubmit={createRoom} className="create-room-form">
            <Input
              value={newRoomName}
              onChange={(e) => setNewRoomName(e.target.value)}
              placeholder="Room name..."
              data-testid="room-name-input"
            />
            <Button type="submit" size="sm" data-testid="submit-room-button">
              Create
            </Button>
          </form>
        )}

        <div className="rooms-list">
          {filteredRooms.map((room) => (
            <div
              key={room.id}
              className={`room-item ${activeRoom?.id === room.id ? "active" : ""}`}
              onClick={() => selectRoom(room)}
              data-testid={`room-item-${room.id}`}
            >
              <div className="room-icon">
                {room.type === "private" ? "@" : "#"}
              </div>
              <div className="room-info">
                <div className="room-name">{room.name}</div>
                <div className="room-members">
                  {room.type === "private" ? "Direct Message" : `${room.members.length} members`}
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="user-info">
            <div className="user-avatar">{user?.username?.[0]?.toUpperCase()}</div>
            <span className="user-name">{user?.username}</span>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={onLogout}
            data-testid="logout-button"
          >
            <LogOut size={18} />
          </Button>
        </div>
      </div>

      <div className="chat-main">
        {activeRoom ? (
          <>
            <div className="chat-header">
              <div>
                <h2 className="chat-title" data-testid="active-room-name">{activeRoom.name}</h2>
                <div className="connection-status">
                  <div className={`status-dot ${connected ? "connected" : ""}`} />
                  <span>{connected ? "Connected" : "Disconnected"}</span>
                  <span className="online-count">
                    • {Object.keys(onlineUsers).length} online
                  </span>
                </div>
              </div>
              {activeRoom.type === "group" && (
                <Dialog open={showAddMember} onOpenChange={setShowAddMember}>
                  <DialogTrigger asChild>
                    <Button
                      size="sm"
                      variant="outline"
                      data-testid="add-member-button"
                    >
                      <UserPlus size={16} className="mr-2" />
                      Add Member
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="dialog-content">
                    <DialogHeader>
                      <DialogTitle>Add Member to {activeRoom.name}</DialogTitle>
                    </DialogHeader>
                    <form onSubmit={addMemberToRoom} className="add-member-form">
                      <Input
                        value={memberEmail}
                        onChange={(e) => setMemberEmail(e.target.value)}
                        placeholder="Enter user email..."
                        type="email"
                        data-testid="member-email-input"
                      />
                      <Button type="submit" data-testid="submit-add-member">
                        Add Member
                      </Button>
                    </form>
                  </DialogContent>
                </Dialog>
              )}
            </div>

            <ScrollArea className="messages-area" ref={scrollRef}>
              <div className="messages-container" data-testid="messages-container">
                {hasMore && (
                  <div style={{ textAlign: "center", padding: "0.5rem" }}>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={loadOlderMessages}
                      disabled={loadingMore}
                    >
                      {loadingMore ? "Loading..." : "Load older messages"}
                    </Button>
                  </div>
                )}
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`message ${msg.user_id === user?.id ? "own" : ""}`}
                    data-testid={`message-${msg.id}`}
                  >
                    <div className="message-avatar">
                      {msg.username?.[0]?.toUpperCase()}
                    </div>
                    <div className="message-content">
                      <div className="message-header">
                        <span className="message-username">{msg.username}</span>
                        <span className="message-time">
                          {new Date(msg.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <div className="message-text">{msg.content}</div>
                      {msg.attachments && msg.attachments.length > 0 && (
                        <div className="message-attachments">
                          {msg.attachments.map((url, idx) => (
                            <a key={idx} href={`${BACKEND_URL}${url}`} target="_blank" rel="noopener noreferrer" className="attachment-link">
                              {url.match(/\.(jpg|jpeg|png|gif|webp)$/i) ? (
                                <img src={`${BACKEND_URL}${url}`} alt="attachment" className="attachment-image" />
                              ) : (
                                <div className="attachment-file">
                                  <Paperclip size={14} /> File Attachment
                                </div>
                              )}
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>

            <form onSubmit={sendMessage} className="message-input-form">
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileUpload}
                style={{ display: 'none' }}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => fileInputRef.current?.click()}
                disabled={!connected || isUploading}
                title="Attach file"
              >
                <Paperclip size={20} />
              </Button>
              <Input
                value={messageInput}
                onChange={(e) => setMessageInput(e.target.value)}
                placeholder={`Message ${activeRoom.type === "private" ? "" : "#"}${activeRoom.name}`}
                disabled={!connected}
                data-testid="message-input"
              />
              <Button
                type="submit"
                disabled={!connected || !messageInput.trim()}
                data-testid="send-message-button"
              >
                <Send size={18} />
              </Button>
            </form>
          </>
        ) : (
          <div className="empty-state">
            <Users size={64} />
            <h3>Select a chat to start messaging</h3>
            <p>Search for users to start a DM or create a new room</p>
          </div>
        )}
      </div>
    </div>
  );
}
