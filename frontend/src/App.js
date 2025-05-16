import React, { useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import './App.css';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function App() {
  const [chatSessions, setChatSessions] = useState([]); // List of chat sessions
  const [currentSession, setCurrentSession] = useState(null); // Current active session
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [profile] = useState({ name: 'Guest', profilePic: '👤' });
  const [logoSrc, setLogoSrc] = useState('/logo.png');
  const [isListening, setIsListening] = useState(false);
  const [selectedModel, setSelectedModel] = useState('basic'); // Default to basic
  const [editingMessageIndex, setEditingMessageIndex] = useState(null); // Track message being edited
  const fileInputRef = useRef(null);

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = SpeechRecognition ? new SpeechRecognition() : null;

  if (recognition) {
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
  }

  // Function to parse Markdown tables from text
  const parseTableFromText = (text) => {
    if (!text || typeof text !== 'string') return null;

    const lines = text.split('\n').filter(line => line.trim() !== '');
    let headers = null;
    const rows = [];
    let isTable = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line.match(/^\|.*\|$/)) {
        const parts = line.split('|').map(item => item.trim()).filter(item => item !== '');
        if (!headers) {
          headers = parts;
          isTable = true;
          if (i + 1 < lines.length && lines[i + 1].match(/^\|[-:\s|]+\|$/)) {
            i++; // Skip separator row
          }
        } else {
          const row = parts;
          if (row.length === headers.length) {
            rows.push(row);
          }
        }
      }
    }

    return isTable && headers && rows.length > 0 ? { headers, rows } : null;
  };

  // Function to download table as CSV
  const downloadTableAsCSV = (tableData, fileName = 'table') => {
    const { headers, rows } = tableData;

    // Escape CSV values (handle commas, quotes, etc.)
    const escapeCSV = (value) => {
      if (typeof value !== 'string') return value;
      if (value.includes(',') || value.includes('"') || value.includes('\n')) {
        return `"${value.replace(/"/g, '""')}"`;
      }
      return value;
    };

    // Create CSV content
    const csvRows = [
      headers.map(escapeCSV).join(','), // Header row
      ...rows.map(row => row.map(escapeCSV).join(',')) // Data rows
    ];
    const csvContent = csvRows.join('\n');

    // Create a Blob and trigger download
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `${fileName}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const startNewSession = (title = 'Untitled Chat') => {
    const newSession = {
      id: Date.now(),
      title,
      messages: [],
      timestamp: new Date(),
    };
    setChatSessions((prev) => [...prev, newSession]);
    setCurrentSession(newSession);
    return newSession;
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (input.trim() === '') return;

    let session = currentSession;
    if (!session) {
      session = startNewSession(input.length > 30 ? input.slice(0, 27) + '...' : input);
    }

    let updatedSession;
    if (editingMessageIndex !== null) {
      const updatedMessages = [...session.messages];
      updatedMessages[editingMessageIndex] = { type: 'text', data: input, raw: input, sender: 'user' };
      if (updatedMessages[editingMessageIndex + 1]?.sender === 'bot') {
        updatedMessages.splice(editingMessageIndex + 1, 1);
      }
      updatedSession = { ...session, messages: updatedMessages };
      setEditingMessageIndex(null);
    } else {
      const newMessage = { type: 'text', data: input, raw: input, sender: 'user' };
      updatedSession = {
        ...session,
        messages: [...session.messages, newMessage],
      };
    }

    setChatSessions((prev) =>
      prev.map((s) => (s.id === session.id ? updatedSession : s))
    );
    setCurrentSession(updatedSession);
    const userPrompt = input;
    setInput('');
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: userPrompt, model: selectedModel, max_new_tokens: 500 }),
      });

      if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);

      const data = await response.json();
      if (data.status === 'success' && data.response) {
        const tableData = parseTableFromText(data.response);
        const botMessage = tableData
          ? { type: 'table', data: tableData, raw: data.response, sender: 'bot' }
          : { type: 'text', data: data.response, raw: data.response, sender: 'bot' };

        const updatedSessionWithBot = {
          ...updatedSession,
          messages: [...updatedSession.messages, botMessage],
        };
        setChatSessions((prev) =>
          prev.map((s) => (s.id === session.id ? updatedSessionWithBot : s))
        );
        setCurrentSession(updatedSessionWithBot);
      } else {
        const errorMessage = { type: 'text', data: `Error: ${data.error || 'Failed to generate response'}`, raw: data.error, sender: 'bot', error: true };
        const updatedSessionWithError = {
          ...updatedSession,
          messages: [...updatedSession.messages, errorMessage],
        };
        setChatSessions((prev) =>
          prev.map((s) => (s.id === session.id ? updatedSessionWithError : s))
        );
        setCurrentSession(updatedSessionWithError);
      }
    } catch (error) {
      const errorMessage = { type: 'text', data: `Error: ${error.message}`, raw: error.message, sender: 'bot', error: true };
      const updatedSessionWithError = {
        ...updatedSession,
        messages: [...updatedSession.messages, errorMessage],
      };
      setChatSessions((prev) =>
        prev.map((s) => (s.id === session.id ? updatedSessionWithError : s))
      );
      setCurrentSession(updatedSessionWithError);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    let session = currentSession;
    if (!session) {
      session = startNewSession(`Uploaded: ${file.name}`);
    }

    const newMessage = { type: 'text', data: `Uploaded file: ${file.name}`, raw: `Uploaded file: ${file.name}`, sender: 'user' };
    const updatedSession = {
      ...session,
      messages: [...session.messages, newMessage],
    };
    setChatSessions((prev) =>
      prev.map((s) => (s.id === session.id ? updatedSession : s))
    );
    setCurrentSession(updatedSession);
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('prompt', 'Process the uploaded file');
      formData.append('model', selectedModel);
      formData.append('max_new_tokens', 500);

      const response = await fetch(`${API_URL}/generate`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);

      const data = await response.json();
      if (data.status === 'success' && data.response) {
        const tableData = parseTableFromText(data.response);
        const botMessage = tableData
          ? { type: 'table', data: tableData, raw: data.response, sender: 'bot' }
          : { type: 'text', data: data.response, raw: data.response, sender: 'bot' };

        const updatedSessionWithBot = {
          ...updatedSession,
          messages: [...updatedSession.messages, botMessage],
        };
        setChatSessions((prev) =>
          prev.map((s) => (s.id === session.id ? updatedSessionWithBot : s))
        );
        setCurrentSession(updatedSessionWithBot);
      } else {
        const errorMessage = { type: 'text', data: `Error: ${data.error || 'Failed to generate response'}`, raw: data.error, sender: 'bot', error: true };
        const updatedSessionWithError = {
          ...updatedSession,
          messages: [...updatedSession.messages, errorMessage],
        };
        setChatSessions((prev) =>
          prev.map((s) => (s.id === session.id ? updatedSessionWithError : s))
        );
        setCurrentSession(updatedSessionWithError);
      }
    } catch (error) {
      const errorMessage = { type: 'text', data: `Error: ${error.message}`, raw: error.message, sender: 'bot', error: true };
      const updatedSessionWithError = {
        ...updatedSession,
        messages: [...updatedSession.messages, errorMessage],
      };
      setChatSessions((prev) =>
        prev.map((s) => (s.id === session.id ? updatedSessionWithError : s))
      );
      setCurrentSession(updatedSessionWithError);
    } finally {
      setLoading(false);
      fileInputRef.current.value = null;
    }
  };

  const handleVoiceInput = () => {
    if (!recognition) {
      const errorMessage = { type: 'text', data: 'Voice input not supported.', raw: 'Voice input not supported.', sender: 'bot', error: true };
      let session = currentSession;
      if (!session) {
        session = startNewSession('Voice Input Error');
      }
      const updatedSession = {
        ...session,
        messages: [...session.messages, errorMessage],
      };
      setChatSessions((prev) =>
        prev.map((s) => (s.id === session.id ? updatedSession : s))
      );
      setCurrentSession(updatedSession);
      return;
    }
    if (isListening) {
      recognition.stop();
      setIsListening(false);
      return;
    }
    setIsListening(true);
    recognition.start();
    recognition.onresult = (event) => {
      setInput(event.results[0][0].transcript);
      setIsListening(false);
    };
    recognition.onerror = (event) => {
      const errorMessage = { type: 'text', data: `Voice input error: ${event.error}`, raw: `Voice input error: ${event.error}`, sender: 'bot', error: true };
      let session = currentSession;
      if (!session) {
        session = startNewSession('Voice Input Error');
      }
      const updatedSession = {
        ...session,
        messages: [...session.messages, errorMessage],
      };
      setChatSessions((prev) =>
        prev.map((s) => (s.id === session.id ? updatedSession : s))
      );
      setCurrentSession(updatedSession);
      setIsListening(false);
    };
    recognition.onend = () => setIsListening(false);
  };

  const handleDeleteSession = (sessionId) => {
    setChatSessions(chatSessions.filter((session) => session.id !== sessionId));
    if (currentSession && currentSession.id === sessionId) {
      setCurrentSession(null);
    }
  };

  const handleEditPrompt = (data, index) => {
    setInput(data);
    setEditingMessageIndex(index);
  };

  const handleCancelEdit = () => {
    setInput('');
    setEditingMessageIndex(null);
  };

  const handleUpdateSessionTitle = (sessionId, newTitle) => {
    const updatedSessions = chatSessions.map((session) =>
      session.id === sessionId ? { ...session, title: newTitle } : session
    );
    setChatSessions(updatedSessions);
    if (currentSession && currentSession.id === sessionId) {
      setCurrentSession({ ...currentSession, title: newTitle });
    }
  };

  const handleSelectSession = (session) => {
    setCurrentSession(session);
    setEditingMessageIndex(null);
  };

  const models = [
    { value: 'basic', label: 'Basic (LLaMA 3 8B)' },
    { value: 'ultra', label: 'Ultra (LLaMA 3 70B)' },
  ];

  const isWithinLast7Days = (timestamp) => {
    const now = new Date();
    const sevenDaysAgo = new Date(now.setDate(now.getDate() - 7));
    return new Date(timestamp) >= sevenDaysAgo;
  };

  return (
    <div className="app">
      <div className="main-container">
        <div className="sidebar">
          <div className="brand-section">
            <img
              src={logoSrc}
              alt="Logo"
              className="sidebar-logo"
              onError={() => setLogoSrc('https://via.placeholder.com/40')}
            />
            <h1 className="brand-name">AI Chatbot</h1>
          </div>
          <div className="conversations">
            <h3>Today</h3>
            {chatSessions
              .filter((session) => {
                const today = new Date();
                const sessionDate = new Date(session.timestamp);
                return (
                  sessionDate.getDate() === today.getDate() &&
                  sessionDate.getMonth() === today.getMonth() &&
                  sessionDate.getFullYear() === today.getFullYear()
                );
              })
              .map((session) => (
                <div
                  key={session.id}
                  className={`conversation-item ${currentSession && currentSession.id === session.id ? 'active' : ''}`}
                >
                  <span
                    onClick={() => handleSelectSession(session)}
                    style={{ flex: 1 }}
                  >
                    {session.title}
                  </span>
                  <button
                    onClick={() => {
                      const newTitle = prompt('Enter new title:', session.title);
                      if (newTitle) handleUpdateSessionTitle(session.id, newTitle);
                    }}
                    className="edit"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDeleteSession(session.id)}
                    className="delete"
                  >
                    Delete
                  </button>
                </div>
              ))}
            <h3>Previous 7 Days</h3>
            {chatSessions
              .filter(
                (session) =>
                  isWithinLast7Days(session.timestamp) &&
                  !(
                    new Date(session.timestamp).getDate() === new Date().getDate() &&
                    new Date(session.timestamp).getMonth() === new Date().getMonth() &&
                    new Date(session.timestamp).getFullYear() === new Date().getFullYear()
                  )
              )
              .map((session) => (
                <div
                  key={session.id}
                  className={`conversation-item ${currentSession && currentSession.id === session.id ? 'active' : ''}`}
                >
                  <span
                    onClick={() => handleSelectSession(session)}
                    style={{ flex: 1 }}
                  >
                    {session.title}
                  </span>
                  <button
                    onClick={() => {
                      const newTitle = prompt('Enter new title:', session.title);
                      if (newTitle) handleUpdateSessionTitle(session.id, newTitle);
                    }}
                    className="edit"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDeleteSession(session.id)}
                    className="delete"
                  >
                    Delete
                  </button>
                </div>
              ))}
            <button className="renew-btn" onClick={() => startNewSession()}>
              New Chat
            </button>
          </div>
        </div>
        <div className="chat-container">
          <header className="header">
            <div className="version-selector">
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="version-dropdown"
              >
                {models.map((model) => (
                  <option key={model.value} value={model.value}>
                    {model.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="profile-section">
              <button className="share-btn">🔗</button>
              <span className="profile-pic">{profile.profilePic}</span>
            </div>
          </header>
          <div className="main-chat">
            {currentSession ? (
              <div>
                <h2>{currentSession.title}</h2>
                <div className="messages">
                  {currentSession.messages.map((msg, index) => {
                    const messageType = msg.type || (msg.text ? 'text' : 'unknown');
                    const messageData = msg.data || msg.text || '';
                    const rawData = msg.raw || msg.text || '';

                    return (
                      <div
                        key={index}
                        className={`message ${msg.sender} ${msg.error ? 'error' : ''}`}
                      >
                        {messageType === 'table' && messageData.headers && messageData.rows ? (
                          <div className="table-container">
                            <table className="response-table">
                              <thead>
                                <tr>
                                  {messageData.headers.map((header, idx) => (
                                    <th key={idx}>{header}</th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {messageData.rows.map((row, rowIdx) => (
                                  <tr key={rowIdx}>
                                    {row.map((cell, cellIdx) => (
                                      <td key={cellIdx}>{cell}</td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                            <button
                              className="download-btn"
                              onClick={() => downloadTableAsCSV(messageData, `table_${index}`)}
                            >
                              Download Table
                            </button>
                          </div>
                        ) : (
                          <ReactMarkdown>{messageData}</ReactMarkdown>
                        )}
                        {msg.sender === 'user' && (
                          <div>
                            <button
                              onClick={() => handleEditPrompt(messageData, index)}
                              className="edit"
                            >
                              Edit
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                  {loading && <div className="loading">Loading...</div>}
                </div>
              </div>
            ) : (
              <div className="welcome-message">
                What can I help with? Try typing a prompt or uploading a file (.txt, .docx, .pdf, or image).
              </div>
            )}
          </div>
          <form className="input-container" onSubmit={handleSendMessage}>
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              accept=".txt,.docx,.pdf,image/*"
              onChange={handleFileUpload}
            />
            <button
              type="button"
              className="attachment-btn"
              onClick={() => fileInputRef.current.click()}
            >
              <img
                src="/attach-icon.png"
                alt="Attach"
                onError={(e) => (e.target.src = 'https://via.placeholder.com/24')}
                style={{ maxWidth: '100%', height: 'auto' }}
              />
            </button>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a prompt or upload a file (.txt, .docx, .pdf, or image)..."
              disabled={loading}
            />
            {editingMessageIndex !== null && (
              <button
                type="button"
                className="cancel-btn"
                onClick={handleCancelEdit}
              >
                Cancel
              </button>
            )}
            <button
              type="button"
              className={`voice-btn ${isListening ? 'listening' : ''}`}
              onClick={handleVoiceInput}
            >
              <img
                src="/voice-icon.png"
                alt="Voice"
                onError={(e) => (e.target.src = 'https://via.placeholder.com/24')}
                style={{ maxWidth: '100%', height: 'auto' }}
              />
            </button>
            <button type="submit" className="send-btn" disabled={loading}>
              {loading ? 'Generating...' : editingMessageIndex !== null ? 'Update' : 'Send'}
            </button>
          </form>
          <div className="disclaimer">
            AI Chatbot can make mistakes. Check important info.
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;