import { useState, useEffect } from 'react'
import './App.css'

const API_BASE = 'http://localhost:8000'

function App() {
  const [apiKey, setApiKey] = useState(localStorage.getItem('apiKey') || '')
  const [tenantId, setTenantId] = useState(null)
  const [tenantName, setTenantName] = useState('')
  const [manualKeyInput, setManualKeyInput] = useState('')

  const [uploadFilename, setUploadFilename] = useState('')
  const [uploadContent, setUploadContent] = useState('')
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
  }

  function handleUseExistingKey() {
    setApiKey(manualKeyInput)
    localStorage.setItem('apiKey', manualKeyInput)
  }

  function handleLogout() {
    setApiKey('')
    localStorage.removeItem('apiKey')
  }

  async function handleUpload() {
    setJobStatus(null)
    setDocumentId(null)
    setJobError(null)

    const response = await fetch(`${API_BASE}/documents`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey,
      },
      body: JSON.stringify({ filename: uploadFilename || 'untitled.txt', content: uploadContent }),
    })
    const data = await response.json()
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
    }, 1500)

    return () => clearInterval(intervalId)
  }, [jobId, jobStatus, apiKey])

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
      body: JSON.stringify({ question: currentQuestion }),
    })
    const data = await response.json()

    setConversation((prev) => [
      ...prev,
      { question: currentQuestion, answer: data.answer, cached: data.cached, chunks: data.chunks_used },
    ])
    setIsAsking(false)
  }

  return (
    <div className="app">
      <h1>repo-qa-service</h1>

      {!apiKey ? (
        <div className="card">
          <h2>Get started</h2>

          <div className="form-row">
            <input
              type="text"
              placeholder="Tenant name (e.g. my-project)"
              value={tenantName}
              onChange={(e) => setTenantName(e.target.value)}
            />
            <button onClick={handleCreateTenant}>Create New Tenant</button>
          </div>

          <p className="divider">Already have an API key?</p>

          <div className="form-row">
            <input
              type="text"
              placeholder="Paste your API key"
              value={manualKeyInput}
              onChange={(e) => setManualKeyInput(e.target.value)}
            />
            <button onClick={handleUseExistingKey}>Use This Key</button>
          </div>
        </div>
      ) : (
        <>
          <div className="card">
            <p>Signed in with API key: <code>{apiKey.slice(0, 12)}...</code></p>
            {tenantId && <p>Tenant ID: {tenantId}</p>}
            <button onClick={handleLogout}>Log out</button>
          </div>

          <div className="card">
            <h2>Upload a document</h2>
            <div className="form-row">
              <input
                type="text"
                placeholder="Filename"
                value={uploadFilename}
                onChange={(e) => setUploadFilename(e.target.value)}
              />
            </div>
            <textarea
              placeholder="Paste document text here..."
              value={uploadContent}
              onChange={(e) => setUploadContent(e.target.value)}
              rows={6}
            />
            <button onClick={handleUpload}>Upload</button>

            {jobStatus && (
              <p className="job-status">
                Job #{jobId}: <strong>{jobStatus}</strong>
                {documentId && ` — document ID ${documentId}`}
                {jobError && ` — error: ${jobError}`}
              </p>
            )}
          </div>

          <div className="card">
            <h2>Ask a question</h2>
            <div className="form-row">
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

            <div className="conversation">
              {conversation.map((item, index) => (
                <div key={index} className="qa-pair">
                  <p className="question-text"><strong>Q:</strong> {item.question}</p>
                  <p className="answer-text">
                    <strong>A:</strong> {item.answer}
                    {item.cached && <span className="cached-badge">cached</span>}
                  </p>
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
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default App
