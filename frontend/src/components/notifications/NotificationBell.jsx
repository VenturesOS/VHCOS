import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { notificationAPI } from '../../lib/api';
import { Bell, Check, CheckCheck, Trash2, Settings, X } from 'lucide-react';
import { Button } from '../ui/button';
import { toast } from 'sonner';

const typeIcon = {
  new_application: 'bg-blue-100 text-blue-600',
  status_change: 'bg-amber-100 text-amber-600',
  job_posted: 'bg-green-100 text-green-600',
  job_assigned: 'bg-purple-100 text-purple-600',
  candidate_assigned: 'bg-cyan-100 text-cyan-600',
  am_company_assigned: 'bg-indigo-100 text-indigo-600',
  system: 'bg-slate-100 text-slate-600',
};

export default function NotificationBell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef(null);

  const fetchCount = useCallback(async () => {
    try {
      const res = await notificationAPI.getUnreadCount();
      setUnreadCount(res.data.count);
    } catch {
      // silent
    }
  }, []);

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const res = await notificationAPI.getAll({ limit: 15 });
      setNotifications(res.data.notifications || []);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  // SSE live stream — replaces the old 120s HTTP poll.
  // Same-worker mutations reach us in ~100ms; cross-worker within 60s
  // via the server-side heartbeat. Browser auto-reconnects on drop.
  // EventSource can't set Authorization headers, so the JWT is passed
  // as ?token=… (server accepts token via query param on this endpoint).
  useEffect(() => {
    const backendUrl = process.env.REACT_APP_BACKEND_URL;
    const token = localStorage.getItem('vhc_token');
    if (!backendUrl || !token) {
      // Not logged in / no backend URL — nothing to stream.
      return undefined;
    }

    let es;
    let reconnectTimer;
    let closed = false;

    const connect = () => {
      if (closed) return;
      const url = `${backendUrl}/api/notifications/stream?token=${encodeURIComponent(token)}`;
      es = new EventSource(url);

      es.addEventListener('count', (evt) => {
        const n = parseInt(evt.data, 10);
        if (!Number.isNaN(n)) setUnreadCount(n);
      });

      es.onerror = () => {
        // EventSource auto-reconnects on transient errors. If the server
        // closes us (auth expired, redeploy), the readyState goes to CLOSED
        // and we must manually schedule a fresh connection with backoff.
        if (es && es.readyState === 2 /* CLOSED */ && !closed) {
          es.close();
          reconnectTimer = setTimeout(connect, 15000);
        }
      };
    };

    connect();

    // Refresh count when the tab regains focus in case the SSE stream is
    // silently stalled behind a broken proxy.
    const onVisible = () => {
      if (!document.hidden) fetchCount();
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (es) es.close();
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [fetchCount]);

  // Load notifications when dropdown opens
  useEffect(() => {
    if (open) fetchNotifications();
  }, [open, fetchNotifications]);

  // Close on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleMarkRead = async (id) => {
    try {
      await notificationAPI.markRead(id);
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n));
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch {
      toast.error('Failed to mark as read');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await notificationAPI.markAllRead();
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
      setUnreadCount(0);
      toast.success('All notifications marked as read');
    } catch {
      toast.error('Failed');
    }
  };

  const handleDelete = async (id) => {
    try {
      await notificationAPI.deleteOne(id);
      setNotifications(prev => prev.filter(n => n.id !== id));
      fetchCount();
    } catch {
      toast.error('Failed to delete');
    }
  };

  const handleClick = (notif) => {
    if (!notif.is_read) handleMarkRead(notif.id);
    if (notif.link) {
      navigate(notif.link);
      setOpen(false);
    }
  };

  const timeAgo = (dateStr) => {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setOpen(!open)}
        className="relative p-2 rounded-lg hover:bg-slate-100 transition-colors"
        data-testid="notification-bell"
      >
        <Bell className="w-5 h-5 text-slate-600" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-5 h-5 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center" data-testid="notification-badge">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute left-0 top-12 w-80 sm:w-96 bg-white rounded-xl shadow-xl border border-slate-200 z-50 overflow-hidden" data-testid="notification-dropdown">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
            <h3 className="font-semibold text-slate-900 text-sm">Notifications</h3>
            <div className="flex items-center gap-1">
              {unreadCount > 0 && (
                <Button variant="ghost" size="sm" onClick={handleMarkAllRead} className="h-7 px-2 text-xs" data-testid="mark-all-read-btn">
                  <CheckCheck className="w-3.5 h-3.5 mr-1" /> Mark all read
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={() => { 
                const rolePrefix = location.pathname.split('/')[1] || 'admin';
                navigate(`/${rolePrefix}/settings/notifications`); 
                setOpen(false); 
              }} className="h-7 px-2 text-xs">
                <Settings className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>

          {/* Notification List */}
          <div className="max-h-96 overflow-y-auto">
            {loading ? (
              <div className="py-8 text-center text-slate-400 text-sm">Loading...</div>
            ) : notifications.length === 0 ? (
              <div className="py-8 text-center text-slate-400 text-sm">No notifications yet</div>
            ) : (
              notifications.map((notif) => (
                <div
                  key={notif.id}
                  className={`flex items-start gap-3 px-4 py-3 border-b border-slate-50 hover:bg-slate-50 cursor-pointer transition-colors ${!notif.is_read ? 'bg-blue-50/50' : ''}`}
                  data-testid={`notification-item-${notif.id}`}
                >
                  <div onClick={() => handleClick(notif)} className="flex-1 flex items-start gap-3 min-w-0">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold ${typeIcon[notif.type] || typeIcon.system}`}>
                      {notif.title?.charAt(0) || 'N'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm leading-snug ${!notif.is_read ? 'font-semibold text-slate-900' : 'text-slate-700'}`}>
                        {notif.title}
                      </p>
                      <p className="text-xs text-slate-500 mt-0.5 truncate">{notif.message}</p>
                      <p className="text-xs text-slate-400 mt-1">{timeAgo(notif.created_at)}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-0.5 shrink-0">
                    {!notif.is_read && (
                      <button onClick={(e) => { e.stopPropagation(); handleMarkRead(notif.id); }} className="p-1 hover:bg-slate-200 rounded" title="Mark as read">
                        <Check className="w-3.5 h-3.5 text-slate-400" />
                      </button>
                    )}
                    <button onClick={(e) => { e.stopPropagation(); handleDelete(notif.id); }} className="p-1 hover:bg-red-100 rounded" title="Delete">
                      <Trash2 className="w-3.5 h-3.5 text-slate-400" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
