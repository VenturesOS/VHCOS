import { useState, useEffect } from 'react';
import { messageAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import { Mail, Inbox, Send, Check, Clock } from 'lucide-react';

export default function MessagesPage() {
  const [inbox, setInbox] = useState([]);
  const [sent, setSent] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedMessage, setSelectedMessage] = useState(null);

  useEffect(() => {
    loadMessages();
  }, []);

  const loadMessages = async () => {
    try {
      const [inboxRes, sentRes] = await Promise.all([
        messageAPI.getInbox(),
        messageAPI.getSent(),
      ]);
      setInbox(inboxRes.data);
      setSent(sentRes.data);
    } catch (error) {
      toast.error('Failed to load messages');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenMessage = async (message) => {
    setSelectedMessage(message);
    if (!message.is_read) {
      try {
        await messageAPI.markRead(message.id);
        setInbox((prev) =>
          prev.map((m) => (m.id === message.id ? { ...m, is_read: true } : m))
        );
      } catch (error) {
        // Ignore
      }
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  const MessageList = ({ messages, type }) => (
    <div className="divide-y divide-slate-100">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`p-4 hover:bg-slate-50 transition-colors cursor-pointer ${
            !msg.is_read && type === 'inbox' ? 'bg-blue-50/50' : ''
          }`}
          onClick={() => handleOpenMessage(msg)}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center shrink-0">
                <span className="text-[#7CB342] font-semibold text-sm">
                  {(type === 'inbox' ? msg.sender_name : msg.recipient_name)?.charAt(0).toUpperCase()}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-medium text-slate-900 truncate">
                    {type === 'inbox' ? msg.sender_name : msg.recipient_name}
                  </p>
                  {!msg.is_read && type === 'inbox' && (
                    <span className="w-2 h-2 bg-[#7CB342] rounded-full" />
                  )}
                </div>
                <p className="text-sm font-medium text-slate-700 truncate">{msg.subject}</p>
                <p className="text-xs text-slate-500 truncate">{msg.content}</p>
              </div>
            </div>
            <p className="text-xs text-slate-400 shrink-0">
              {new Date(msg.created_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}
            </p>
          </div>
        </div>
      ))}
      {messages.length === 0 && (
        <div className="p-8 text-center">
          <Mail className="w-12 h-12 text-slate-300 mx-auto mb-2" />
          <p className="text-slate-500">No messages</p>
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-6" data-testid="messages-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Messages</h1>
        <p className="text-slate-500 mt-1">Your inbox and sent messages</p>
      </div>

      <Card className="border-slate-200">
        <CardContent className="p-0">
          <Tabs defaultValue="inbox">
            <div className="border-b border-slate-200 px-4">
              <TabsList className="bg-transparent">
                <TabsTrigger value="inbox" className="data-[state=active]:bg-[#DCFCE7] data-[state=active]:text-[#7CB342]">
                  <Inbox className="w-4 h-4 mr-2" />
                  Inbox ({inbox.filter((m) => !m.is_read).length})
                </TabsTrigger>
                <TabsTrigger value="sent" className="data-[state=active]:bg-[#DCFCE7] data-[state=active]:text-[#7CB342]">
                  <Send className="w-4 h-4 mr-2" />
                  Sent
                </TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value="inbox" className="m-0">
              <MessageList messages={inbox} type="inbox" />
            </TabsContent>
            <TabsContent value="sent" className="m-0">
              <MessageList messages={sent} type="sent" />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      {/* Message Detail Dialog */}
      <Dialog open={!!selectedMessage} onOpenChange={() => setSelectedMessage(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-heading">{selectedMessage?.subject}</DialogTitle>
          </DialogHeader>
          {selectedMessage && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                  <span className="text-[#7CB342] font-bold">
                    {selectedMessage.sender_name?.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <p className="font-medium">{selectedMessage.sender_name}</p>
                  <p className="text-sm text-slate-500">
                    {new Date(selectedMessage.created_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}
                  </p>
                </div>
              </div>
              <div className="bg-slate-50 p-4 rounded-lg">
                <p className="text-slate-700 whitespace-pre-wrap">{selectedMessage.content}</p>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
