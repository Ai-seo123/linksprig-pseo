import { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { UploadCloud, CheckCircle, XCircle, LogOut, Loader2, Sparkles, Download, Send } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL !== undefined && import.meta.env.VITE_API_URL !== ''
  ? import.meta.env.VITE_API_URL 
  : (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') ? 'http://127.0.0.1:8000' : '');

const Dashboard = ({ token, onLogout }) => {
  const [activeTab, setActiveTab] = useState('pipeline'); // 'pipeline' or 'ideas'
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [statusMap, setStatusMap] = useState({});

  // Idea Generation state
  const [promptText, setPromptText] = useState('');
  const [ideas, setIdeas] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [generationError, setGenerationError] = useState('');
  const [importing, setImporting] = useState(false);

  const generateTopics = async () => {
    if (!promptText.trim()) return;
    setGenerating(true);
    setGenerationError('');
    setIdeas([]);

    try {
      const response = await fetch(`${API_BASE_URL}/api/generate-topics`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ prompt: promptText })
      });

      if (response.status === 401) {
        onLogout();
        return;
      }

      const data = await response.json();
      if (response.ok) {
        setIdeas(data.topics || []);
      } else {
        setGenerationError(data.detail || 'Failed to generate topics.');
      }
    } catch (err) {
      setGenerationError('Network error while generating topics.');
    } finally {
      setGenerating(false);
    }
  };

  const exportToCSV = () => {
    if (ideas.length === 0) return;
    
    const headers = ['Keyword', 'Topic', 'Category'];
    const rows = ideas.map(idea => [
      `"${(idea.keyword || '').replace(/"/g, '""')}"`,
      `"${(idea.topic || '').replace(/"/g, '""')}"`,
      `"${(idea.category || '').replace(/"/g, '""')}"`
    ]);
    
    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    
    const cleanPrompt = promptText.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 30);
    link.setAttribute('download', `generated-topics-${cleanPrompt || 'seo'}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const importToPipeline = async () => {
    if (ideas.length === 0) return;
    setImporting(true);

    const jsonContent = JSON.stringify(ideas, null, 2);
    const blob = new Blob([jsonContent], { type: 'application/json' });
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const fileName = `generated-topics-${timestamp}.json`;
    const file = new File([blob], fileName, { type: 'application/json' });

    setFiles(prev => {
      const existingNames = new Set(prev.map(f => f.name));
      if (existingNames.has(fileName)) return prev;
      return [...prev, file];
    });

    setStatusMap(prev => ({
      ...prev,
      [fileName]: { state: 'uploading', message: 'Uploading to server...' }
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
          [fileName]: { state: 'queued', message: 'Queued for processing' }
        }));
        setActiveTab('pipeline');
      } else {
        setStatusMap(prev => ({
          ...prev,
          [fileName]: { state: 'error', message: data.detail || 'Upload failed' }
        }));
      }
    } catch (err) {
      setStatusMap(prev => ({
        ...prev,
        [fileName]: { state: 'error', message: 'Network error' }
      }));
    } finally {
      setImporting(false);
    }
  };

  const triggerMigration = async () => {
    const jobName = 'migrate_existing_posts_images.py';
    
    setStatusMap(prev => ({
      ...prev,
      [jobName]: { state: 'queued', message: 'Queued for processing' }
    }));

    try {
      const response = await fetch(`${API_BASE_URL}/api/migrate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.status === 401) {
        onLogout();
        return;
      }

      const data = await response.json();

      if (response.ok) {
        setStatusMap(prev => ({
          ...prev,
          [jobName]: { state: 'queued', message: 'Queued for processing' }
        }));
      } else {
        setStatusMap(prev => ({
          ...prev,
          [jobName]: { state: 'error', message: data.detail || 'Migration trigger failed' }
        }));
      }
    } catch (err) {
      setStatusMap(prev => ({
        ...prev,
        [jobName]: { state: 'error', message: 'Network error triggering migration' }
      }));
    }
  };

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
          const existingFiles = Object.keys(jobs)
            .filter(name => name !== 'migrate_existing_posts_images.py')
            .map(name => ({ name }));
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

      <div className="tabs-container">
        <button 
          onClick={() => setActiveTab('pipeline')} 
          className={`tab-btn ${activeTab === 'pipeline' ? 'active' : ''}`}
        >
          WordPress Pipeline
        </button>
        <button 
          onClick={() => setActiveTab('ideas')} 
          className={`tab-btn ${activeTab === 'ideas' ? 'active' : ''}`}
        >
          Topic Generator
        </button>
      </div>

      {activeTab === 'pipeline' ? (
        <>
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

          <div style={{ marginTop: '2.5rem', borderTop: '1px solid var(--surface-border)', paddingTop: '2rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'linear-gradient(to right, #fff, #94a3b8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              <Sparkles size={18} color="var(--primary-color)" style={{ stroke: 'var(--primary-color)' }} /> Retroactive CPT Migration
            </h3>
            <p className="subtitle" style={{ fontSize: '0.875rem', marginBottom: '1.25rem', color: 'var(--text-secondary)' }}>
              Update previously generated draft posts on WordPress to apply Pexels image center-cropping (1704x923) and CSS native title header styling overrides.
            </p>

            {statusMap['migrate_existing_posts_images.py'] && (
              <div style={{ marginBottom: '1.25rem' }}>
                <div className={`pipeline-status-banner pipeline-status-${statusMap['migrate_existing_posts_images.py'].state === 'queued' || statusMap['migrate_existing_posts_images.py'].state === 'processing' ? 'running' : statusMap['migrate_existing_posts_images.py'].state}`} style={{ marginTop: 0 }}>
                  {statusMap['migrate_existing_posts_images.py'].state === 'processing' && <Loader2 className="animate-spin" size={20} color="#fbbf24" />}
                  {statusMap['migrate_existing_posts_images.py'].state === 'queued' && <Loader2 className="animate-pulse" size={20} color="#818cf8" />}
                  {statusMap['migrate_existing_posts_images.py'].state === 'success' && <CheckCircle size={20} color="#34d399" />}
                  {statusMap['migrate_existing_posts_images.py'].state === 'error' && <XCircle size={20} color="#f87171" />}
                  <span style={{ marginLeft: '0.5rem' }}>
                    Migration: {statusMap['migrate_existing_posts_images.py'].message}
                  </span>
                </div>
              </div>
            )}

            <button
              className="primary-btn"
              style={{ background: 'linear-gradient(135deg, #a855f7, #6366f1)', width: '100%' }}
              onClick={triggerMigration}
              disabled={
                statusMap['migrate_existing_posts_images.py']?.state === 'queued' ||
                statusMap['migrate_existing_posts_images.py']?.state === 'processing'
              }
            >
              {statusMap['migrate_existing_posts_images.py']?.state === 'processing' || statusMap['migrate_existing_posts_images.py']?.state === 'queued' ? (
                <Loader2 className="animate-spin" size={20} />
              ) : (
                <Sparkles size={20} />
              )}
              {statusMap['migrate_existing_posts_images.py']?.state === 'processing' || statusMap['migrate_existing_posts_images.py']?.state === 'queued'
                ? 'Running CPT Migration...'
                : 'Start WordPress CPT Migration'}
            </button>
          </div>
        </>
      ) : (
        <div className="ideas-panel">
          <div className="prompt-container">
            <label htmlFor="prompt-input" style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)' }}>
              Enter a prompt to generate keywords and topics
            </label>
            <textarea
              id="prompt-input"
              className="prompt-textarea"
              placeholder="e.g. Give me 5 ideas for LinkedIn outreach strategy guides targeting sales executives"
              value={promptText}
              onChange={(e) => setPromptText(e.target.value)}
              disabled={generating || importing}
            />
          </div>

          {generationError && (
            <div className="pipeline-status-banner pipeline-status-error" style={{ marginTop: 0 }}>
              <XCircle size={20} color="#f87171" />
              <span>{generationError}</span>
            </div>
          )}

          <button
            className="primary-btn"
            onClick={generateTopics}
            disabled={generating || importing || !promptText.trim()}
          >
            {generating ? <Loader2 className="animate-spin" size={20} /> : <Sparkles size={20} />}
            {generating ? 'Generating Ideas...' : 'Generate Keywords & Topics'}
          </button>

          {ideas.length > 0 && (
            <div style={{ marginTop: '2rem' }}>
              <h3 style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>Generated Ideas</h3>
              <div className="table-container">
                <table className="ideas-table">
                  <thead>
                    <tr>
                      <th>Keyword</th>
                      <th>Topic / Title</th>
                      <th>Category</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ideas.map((idea, index) => (
                      <tr key={index}>
                        <td style={{ fontWeight: 600 }}>{idea.keyword}</td>
                        <td>{idea.topic}</td>
                        <td>
                          <span className="status-badge status-success" style={{ textTransform: 'none', background: 'rgba(99, 102, 241, 0.1)', color: '#a5b4fc', border: '1px solid rgba(99, 102, 241, 0.3)' }}>
                            {idea.category}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="action-bar">
                <button
                  className="secondary-btn"
                  onClick={exportToCSV}
                  disabled={importing}
                >
                  <Download size={18} /> Export to CSV
                </button>
                <button
                  className="primary-btn"
                  style={{ width: 'auto' }}
                  onClick={importToPipeline}
                  disabled={importing}
                >
                  {importing ? <Loader2 className="animate-spin" size={18} /> : <Send size={18} />}
                  {importing ? 'Importing...' : 'Straight Import into Queue'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Dashboard;

