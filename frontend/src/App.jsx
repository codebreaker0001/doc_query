import { useState, useEffect } from 'react'
import './App.css'

const API_BASE = 'http://localhost:8000'

function App() {
  const [apiKey, setApiKey] = useState(localStorage.getItem('apiKey') || '')
  const [tenantId, setTenantId] = useState(null)
  const [tenantName, setTenantName] = useState('')
  const [manualKeyInput, setManualKeyInput] = useState('')
  const [showKeyReveal, setShowKeyReveal] = useState(false)
  const [copied, setCopied] = useState(false)

  const [selectedFile, setSelectedFile] = useState(null)
  const [documents, setDocuments] = useState([])
  const [selectedDocumentId, setSelectedDocumentId] = useState('')

  const [jobId, setJobId] = useState(null)
  const [jobStatus, setJobStatus] = useState(null)
  const [documentId, setDocumentId] = useState(null)
  const [jobError, setJobError] = useState(null)

  const [question, setQuestion] = useState('')
  const [conversation, setConversation] = useState([])
  const [isAsking, setIsAsking] = useState(false)

  async function handleCreateTenant() {
    const response = await fetch(`${API_BASE}/tenants`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: tenantName || 'my-tenant' }),
    })
    const data = await response.json()
    setApiKey(data.api_key)
    setTenantId(data.tenant_id)
    localStorage.setItem('apiKey', data.api_key)
    setShowKeyReveal(true)
  }

  function handleUseExistingKey() {
    setApiKey(manualKeyInput)
    localStorage.setItem('apiKey', manualKeyInput)
  }

  function handleLogout() {
    setApiKey('')
    localStorage.removeItem('apiKey')
    setShowKeyReveal(false)
  }

  function handleCopyKey() {
    navigator.clipboard.writeText(apiKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function handleUpload() {
  if (!selectedFile) return

  setJobStatus(null)
  setDocumentId(null)
  setJobError(null)

  const formData = new FormData()
  formData.append('file', selectedFile)

  const response = await fetch(`${API_BASE}/documents`, {
    method: 'POST',
    headers: {
      'X-API-Key': apiKey,
    },
    body: formData,
  })
  const data = await response.json()

  if (!response.ok) {
    setJobError(data.detail || 'Upload failed')
    return
  }

  setJobId(data.job_id)
  setJobStatus(data.status)
}



  useEffect(() => {
    if (!jobId || jobStatus === 'done' || jobStatus === 'failed') {
      return
    }

    const intervalId = setInterval(async () => {
      const response = await fetch(`${API_BASE}/jobs/${jobId}`, {
        headers: { 'X-API-Key': apiKey },
      })
      const data = await response.json()
      setJobStatus(data.status)
      setDocumentId(data.document_id)
      setJobError(data.error_message)
      if (data.status === 'done') {
        refreshDocuments()
      }

    }, 1500)

    return () => clearInterval(intervalId)
  }, [jobId, jobStatus, apiKey])

    async function refreshDocuments() {
      const response = await fetch(`${API_BASE}/documents`, {
        headers: { 'X-API-Key': apiKey },
      })
      if (!response.ok) {
        setDocuments([])
        return
      }
      const data = await response.json()
      setDocuments(data)
    }

    useEffect(() => {
      if (apiKey) refreshDocuments()
    }, [apiKey])


  async function handleQuery() {
    if (!question.trim()) return

    setIsAsking(true)
    const currentQuestion = question
    setQuestion('')

    const response = await fetch(`${API_BASE}/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey,
      },
      body: JSON.stringify({
      question: currentQuestion,
      document_id: selectedDocumentId ? Number(selectedDocumentId) : null,
    }),

    })
    const data = await response.json()

    setConversation((prev) => [
      ...prev,
      { question: currentQuestion, answer: data.answer, cached: data.cached, chunks: data.chunks_used },
    ])
    setIsAsking(false)
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">repo-qa-service</div>

        {!apiKey ? (
          <div className="panel">
            <h2>Get started</h2>
            <div className="form-col">
              <input
                type="text"
                placeholder="Tenant name (e.g. my-project)"
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
              />
              <button onClick={handleCreateTenant}>Create New Tenant</button>
            </div>
            <p className="divider">or</p>
            <div className="form-col">
              <input
                type="text"
                placeholder="Paste your API key"
                value={manualKeyInput}
                onChange={(e) => setManualKeyInput(e.target.value)}
              />
              <button className="secondary" onClick={handleUseExistingKey}>Use Existing Key</button>
            </div>
          </div>
        ) : showKeyReveal ? (
          <div className="panel">
            <h2>Save your API key</h2>
            <p>This is the only time you'll see the full key — it can't be shown again. Copy it somewhere safe.</p>
            <code className="key-reveal">{apiKey}</code>
            <div className="form-col">
              <button onClick={handleCopyKey}>{copied ? 'Copied!' : 'Copy key'}</button>
              <button className="secondary" onClick={() => setShowKeyReveal(false)}>I've saved it, continue</button>
            </div>
          </div>
        ) : (
          <>
            <div className="panel">
              <div className="tenant-info">
                <span className="label">API Key</span>
                <code>{apiKey.slice(0, 12)}...</code>
                {tenantId && (
                  <>
                    <span className="label">Tenant</span>
                    <span>{tenantId}</span>
                  </>
                )}
              </div>
              <button className="secondary small" onClick={handleLogout}>Log out</button>
            </div>

            <div className="panel">
              <h2>Upload document</h2>
              <div className="form-col">
                <input
                  type="file"
                  accept="application/pdf"
                  onChange={(e) => setSelectedFile(e.target.files[0] || null)}
                />
                <button onClick={handleUpload} disabled={!selectedFile}>Upload</button>
              </div>
              {(jobStatus || jobError) && (
                <p className={`job-status status-${jobStatus}`}>
                  {jobStatus && `Job #${jobId}: ${jobStatus}`}
                  {documentId && ` · doc ${documentId}`}
                  {jobError && ` · ${jobError}`}
                </p>
              )}

            </div>
            <div className="panel">
              <h2>Ask about</h2>
              <select value={selectedDocumentId} onChange={(e) => setSelectedDocumentId(e.target.value)}>
                <option value="">All documents</option>
                {documents.map((doc) => (
                  <option key={doc.id} value={doc.id}>{doc.filename}</option>
                ))}
              </select>
            </div>


          </>
        )}
      </aside>

      <main className="main-panel">
        {!apiKey ? (
          <div className="empty-state">
            <p>Sign in or create a tenant to get started</p>
          </div>
        ) : (
          <>
            <div className="chat-scroll">
              {conversation.length === 0 && (
                <div className="empty-state">
                  <p>Upload a document, then ask a question about it</p>
                </div>
              )}
              {conversation.map((item, index) => (
                <div key={index} className="qa-pair">
                  <div className="bubble bubble-question">{item.question}</div>
                  <div className="bubble bubble-answer">
                    {item.answer}
                    {item.cached && <span className="cached-badge">cached</span>}
                    {item.chunks && item.chunks.length > 0 && (
                      <details>
                        <summary>Sources ({item.chunks.length})</summary>
                        <ul>
                          {item.chunks.map((chunk, i) => (
                            <li key={i}>{chunk}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="ask-bar">
              <div className="ask-bar-inner">
                <input
                  type="text"
                  placeholder="Ask something about your uploaded documents..."
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
                />
                <button onClick={handleQuery} disabled={isAsking}>
                  {isAsking ? 'Asking...' : 'Ask'}
                </button>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  )
}

export default App
