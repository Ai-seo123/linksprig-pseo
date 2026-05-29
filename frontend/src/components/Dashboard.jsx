import { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { UploadCloud, CheckCircle, XCircle, LogOut, Loader2 } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL !== undefined && import.meta.env.VITE_API_URL !== ''
  ? import.meta.env.VITE_API_URL 
  : (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') ? 'http://127.0.0.1:8000' : '');

const Dashboard = ({ token, onLogout }) => {
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [statusMap, setStatusMap] = useState({});

  // Fetch existing background jobs on mount
  useEffect(() => {
    const fetchExistingJobs = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/jobs`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        if (response.ok) {
          const jobs = await response.json();
          const existingFiles = Object.keys(jobs).map(name => ({ name }));
          if (existingFiles.length > 0) {
            setFiles(existingFiles);
            const statuses = {};
            Object.keys(jobs).forEach(name => {
              const serverJob = jobs[name];
              let state = 'pending';
              let message = '';
              if (serverJob.status === 'queued') {
                state = 'queued';
                message = 'Queued for processing';
              } else if (serverJob.status === 'processing') {
                state = 'processing';
                message = 'Processing...';
              } else if (serverJob.status === 'completed') {
                state = 'success';
                message = 'Finished successfully';
              } else if (serverJob.status === 'failed') {
                state = 'error';
                message = serverJob.error || 'Processing failed';
              }
              statuses[name] = { state, message };
            });
            setStatusMap(statuses);
          }
        } else if (response.status === 401) {
          onLogout();
        }
      } catch (err) {
        console.error('Error fetching existing jobs:', err);
      }
    };
    fetchExistingJobs();
  }, [token]);

  // Poll jobs status if any job is queued or processing
  useEffect(() => {
    const activeJobsExist = Object.values(statusMap).some(
      s => s.state === 'queued' || s.state === 'processing'
    );

    if (!activeJobsExist) return;

    let timerId;

    const pollJobs = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/jobs`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        if (response.ok) {
          const jobs = await response.json();
          setStatusMap(prev => {
            const updated = { ...prev };
            let hasChanges = false;
            
            Object.keys(updated).forEach(fileName => {
              const serverJob = jobs[fileName];
              if (serverJob) {
                let newState = 'pending';
                let newMessage = '';
                
                if (serverJob.status === 'queued') {
                  newState = 'queued';
                  newMessage = 'Queued for processing';
                } else if (serverJob.status === 'processing') {
                  newState = 'processing';
                  newMessage = 'Processing...';
                } else if (serverJob.status === 'completed') {
                  newState = 'success';
                  newMessage = 'Finished successfully';
                } else if (serverJob.status === 'failed') {
                  newState = 'error';
                  newMessage = serverJob.error || 'Processing failed';
                }

                if (!updated[fileName] || updated[fileName].state !== newState || updated[fileName].message !== newMessage) {
                  updated[fileName] = { state: newState, message: newMessage };
                  hasChanges = true;
                }
              }
            });

            return hasChanges ? updated : prev;
          });
        } else if (response.status === 401) {
          onLogout();
        }
      } catch (err) {
        console.error('Error polling jobs:', err);
      }
    };

    pollJobs();
    timerId = setInterval(pollJobs, 2000);

    return () => clearInterval(timerId);
  }, [statusMap, token]);

  const onDrop = useCallback((acceptedFiles) => {
    setFiles(prev => {
      // Avoid duplicate file objects in state
      const existingNames = new Set(prev.map(f => f.name));
      const filtered = acceptedFiles.filter(f => !existingNames.has(f.name));
      return [...prev, ...filtered];
    });

    const newStatuses = {};
    acceptedFiles.forEach(f => {
      newStatuses[f.name] = { state: 'pending', message: 'Ready to upload' };
    });
    setStatusMap(prev => ({ ...prev, ...newStatuses }));
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/html': ['.html'],
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx']
    }
  });

  const processUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);

    for (const file of files) {
      // Only upload if it's currently pending or has an error status
      const currentState = statusMap[file.name]?.state;
      if (currentState === 'success' || currentState === 'queued' || currentState === 'processing') {
        continue;
      }

      setStatusMap(prev => ({
        ...prev,
        [file.name]: { state: 'uploading', message: 'Uploading to server...' }
      }));

      const formData = new FormData();
      formData.append('file', file);

      try {
        const response = await fetch(`${API_BASE_URL}/api/upload`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          },
          body: formData
        });

        if (response.status === 401) {
          onLogout();
          return;
        }

        const data = await response.json();

        if (response.ok) {
          setStatusMap(prev => ({
            ...prev,
            [file.name]: { state: 'queued', message: 'Queued for processing' }
          }));
        } else {
          setStatusMap(prev => ({
            ...prev,
            [file.name]: { state: 'error', message: data.detail || 'Upload failed' }
          }));
        }
      } catch (err) {
        setStatusMap(prev => ({
          ...prev,
          [file.name]: { state: 'error', message: 'Network error' }
        }));
      }
    }
    
    setUploading(false);
  };

  const removeFile = (fileName) => {
    setFiles(prev => prev.filter(f => f.name !== fileName));
    setStatusMap(prev => {
      const newMap = { ...prev };
      delete newMap[fileName];
      return newMap;
    });
  };

  // Determine global pipeline status
  const getPipelineStatus = () => {
    const statuses = Object.values(statusMap);
    if (statuses.length === 0) return null;

    const isRunning = statuses.some(
      s => s.state === 'uploading' || s.state === 'queued' || s.state === 'processing'
    );
    if (isRunning) {
      return {
        type: 'running',
        message: 'Pipeline is executing in the background...',
        icon: <Loader2 className="animate-spin" size={20} color="#818cf8" />
      };
    }

    const allCompleted = statuses.every(s => s.state === 'success' || s.state === 'error');
    if (allCompleted) {
      const hasSuccess = statuses.some(s => s.state === 'success');
      if (hasSuccess) {
        return {
          type: 'success',
          message: 'Pipeline finished execution successfully!',
          icon: <CheckCircle size={20} color="#34d399" />
        };
      }
      const hasError = statuses.some(s => s.state === 'error');
      if (hasError) {
        return {
          type: 'error',
          message: 'Pipeline completed with errors.',
          icon: <XCircle size={20} color="#f87171" />
        };
      }
    }

    return null;
  };

  const pipelineStatus = getPipelineStatus();

  return (
    <div className="glass-panel dashboard-panel">
      <div className="app-header">
        <div>
          <h1>LinkSprig Engine</h1>
          <p className="subtitle" style={{marginBottom: 0}}>WordPress Pipeline Dashboard</p>
        </div>
        <button onClick={onLogout} className="logout-btn flex items-center gap-2">
          <LogOut size={16} /> Logout
        </button>
      </div>

      {pipelineStatus && (
        <div className={`pipeline-status-banner pipeline-status-${pipelineStatus.type}`}>
          {pipelineStatus.icon}
          <span>{pipelineStatus.message}</span>
        </div>
      )}

      <div 
        {...getRootProps()} 
        className={`dropzone ${isDragActive ? 'active' : ''}`}
      >
        <input {...getInputProps()} />
        <UploadCloud size={48} className="drop-icon" />
        {isDragActive ? (
          <p>Drop the files here ...</p>
        ) : (
          <p>Drag and drop HTML, CSV, or Excel files here, or click to select files</p>
        )}
      </div>

      {files.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>Queued Files</h3>
          <ul className="file-list">
            {files.map(file => {
              const status = statusMap[file.name] || {};
              const badgeClass = status.state === 'uploading' || status.state === 'queued' 
                ? 'pending' 
                : status.state;
              return (
                <li key={file.name} className="file-item">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <span style={{ fontWeight: 500 }}>{file.name}</span>
                    <span className={`status-badge status-${badgeClass}`}>
                      {status.message}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {status.state !== 'uploading' && status.state !== 'queued' && status.state !== 'processing' && (
                      <button 
                        onClick={() => removeFile(file.name)}
                        style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                      >
                        <XCircle size={20} />
                      </button>
                    )}
                    {status.state === 'success' && <CheckCircle size={20} color="#10b981" />}
                    {status.state === 'processing' && <Loader2 className="animate-spin" size={20} color="#fbbf24" />}
                    {status.state === 'queued' && <Loader2 className="animate-pulse" size={20} color="#818cf8" />}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <button 
        className="primary-btn" 
        onClick={processUpload}
        disabled={
          uploading || 
          files.length === 0 || 
          files.every(f => {
            const st = statusMap[f.name]?.state;
            return st === 'success' || st === 'queued' || st === 'processing';
          })
        }
      >
        {uploading ? <Loader2 className="animate-spin" size={20} /> : <UploadCloud size={20} />}
        {uploading ? 'Processing...' : 'Upload and Process Queue'}
      </button>
    </div>
  );
};

export default Dashboard;

