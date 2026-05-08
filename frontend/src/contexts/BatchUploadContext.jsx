import { createContext, useContext, useState, useRef, useCallback } from 'react';
import { cvUploadAPI } from '../lib/api';

const BatchUploadContext = createContext(null);

export function BatchUploadProvider({ children }) {
  // tasks: [{ id, filename, taskId, status: 'queued'|'uploading'|'parsing'|'completed'|'failed', result, error }]
  const [tasks, setTasks] = useState([]);
  const [isActive, setIsActive] = useState(false);
  const abortRef = useRef(false);

  const updateTask = useCallback((id, updates) => {
    setTasks(prev => prev.map(t => t.id === id ? { ...t, ...updates } : t));
  }, []);

  const startBatch = useCallback(async (files) => {
    if (isActive) return;
    abortRef.current = false;

    const newTasks = files.map((file, i) => ({
      id: `batch-${Date.now()}-${i}`,
      filename: file.name,
      file,
      taskId: null,
      status: 'queued',
      result: null,
      error: null,
    }));

    setTasks(newTasks);
    setIsActive(true);

    // Process sequentially in background
    for (let i = 0; i < newTasks.length; i++) {
      if (abortRef.current) break;
      const task = newTasks[i];

      // Mark uploading
      setTasks(prev => prev.map(t => t.id === task.id ? { ...t, status: 'uploading' } : t));

      try {
        // Fire async parse
        const res = await cvUploadAPI.parse(task.file);
        const taskId = res.data.task_id;
        setTasks(prev => prev.map(t => t.id === task.id ? { ...t, taskId, status: 'parsing' } : t));

        // Poll until done
        const result = await pollUntilDone(taskId);
        setTasks(prev => prev.map(t => t.id === task.id ? { ...t, status: 'completed', result } : t));
      } catch (err) {
        const errMsg = err?.response?.data?.detail || err?.message || 'Parse failed';
        setTasks(prev => prev.map(t => t.id === task.id ? { ...t, status: 'failed', error: errMsg } : t));
      }
    }

    setIsActive(false);
  }, [isActive]);

  const clearTasks = useCallback(() => {
    if (!isActive) { setTasks([]); }
  }, [isActive]);

  const cancelBatch = useCallback(() => {
    abortRef.current = true;
  }, []);

  const stats = {
    total: tasks.length,
    completed: tasks.filter(t => t.status === 'completed').length,
    failed: tasks.filter(t => t.status === 'failed').length,
    processing: tasks.filter(t => ['uploading', 'parsing'].includes(t.status)).length,
    queued: tasks.filter(t => t.status === 'queued').length,
  };

  return (
    <BatchUploadContext.Provider value={{ tasks, isActive, stats, startBatch, clearTasks, cancelBatch }}>
      {children}
    </BatchUploadContext.Provider>
  );
}

export function useBatchUpload() {
  const ctx = useContext(BatchUploadContext);
  if (!ctx) throw new Error('useBatchUpload must be used within BatchUploadProvider');
  return ctx;
}

async function pollUntilDone(taskId, maxAttempts = 90, interval = 3000) {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, interval));
    const res = await cvUploadAPI.getParseStatus(taskId);
    if (res.data.status === 'completed') return res.data.result;
    if (res.data.status === 'failed') throw new Error(res.data.error || 'Parsing failed');
  }
  throw new Error('CV parsing timed out');
}
