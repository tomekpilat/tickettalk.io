import { useEffect, useMemo, useState } from 'react'
import { api } from './lib/api.js'

const scale = ['0', '1', '2', '3', '5', '8', '13', '21', '?']
const team = [
  { name: 'You', initials: 'TP' },
  { name: 'Maya', initials: 'MO' },
  { name: 'Alex', initials: 'AK' },
  { name: 'Jo', initials: 'JL' },
]
const fallbackRooms = [{
  id: 'demo-room', name: 'Sprint 42 · Checkout', ticket_count: 5,
  sized_count: 2, total_points: 8, scale: 'fibonacci',
}]
const fallbackTickets = [
  { id: 'demo-0', issue_key: 'PAY-118', summary: 'Split payout ledger by currency', issue_type: 'Story', story_points: 5, description: 'Create independent ledger entries for each payout currency and preserve a clear audit trail.' },
  { id: 'demo-1', issue_key: 'PAY-124', summary: 'Add payment retry schedule', issue_type: 'Story', story_points: 3, description: 'Retry failed collection attempts according to the account policy.' },
  { id: 'demo-2', issue_key: 'PAY-131', summary: 'Surface failed transfer reason', issue_type: 'Bug', story_points: null, description: 'Show the provider failure reason in the transfer detail panel for support teams.' },
  { id: 'demo-3', issue_key: 'PAY-136', summary: 'Support partial refunds', issue_type: 'Story', story_points: null, description: 'Allow operators to refund any amount up to the original captured total.' },
  { id: 'demo-4', issue_key: 'PAY-142', summary: 'Export settlement report', issue_type: 'Task', story_points: null, description: 'Generate a finance-ready settlement report in CSV format.' },
]

function Logo() {
  return <div className="logo"><span>ticket<strong>talks.</strong></span></div>
}

function App() {
  const [view, setView] = useState('rooms')
  const [rooms, setRooms] = useState(fallbackRooms)
  const [room, setRoom] = useState(fallbackRooms[0])
  const [tickets, setTickets] = useState(fallbackTickets)
  const [ticketIndex, setTicketIndex] = useState(2)
  const [selectedVote, setSelectedVote] = useState(null)
  const [revealed, setRevealed] = useState(false)
  const [showDetail, setShowDetail] = useState(false)
  const [roomName, setRoomName] = useState('Sprint 43 planning')
  const [importText, setImportText] = useState('Issue key,Summary,Issue Type\nPAY-201,Add wallet balance alert,Story\nPAY-205,Fix duplicate webhook delivery,Bug')
  const [apiOnline, setApiOnline] = useState(false)

  useEffect(() => {
    api.rooms().then((data) => {
      setRooms(data)
      setApiOnline(true)
    }).catch(() => setApiOnline(false))
  }, [])

  const current = tickets[ticketIndex] || tickets[0]
  const completion = tickets.length ? Math.round((tickets.filter((item) => item.story_points != null).length / tickets.length) * 100) : 0
  const nextUnsizedIndex = tickets.findIndex((item) => item.story_points == null)

  const loadRoom = async (nextRoom) => {
    setRoom(nextRoom)
    try {
      const data = await api.tickets(nextRoom.id)
      if (data.length) setTickets(data)
    } catch { /* demo data stays available */ }
    setView('backlog')
  }

  const parsedTickets = useMemo(() => {
    const rows = importText.trim().split('\n').filter(Boolean)
    const hasHeader = rows[0]?.toLowerCase().includes('summary')
    return rows.slice(hasHeader ? 1 : 0).map((row, index) => {
      const [key, summary, type] = row.split(',').map((part) => part?.trim())
      return { id: `new-${index}`, issue_key: key || `TT-${index + 1}`, summary: summary || key, issue_type: type || 'Story', description: '', story_points: null }
    })
  }, [importText])

  const createRoom = async () => {
    const localRoom = { id: `local-${Date.now()}`, name: roomName, scale: 'fibonacci', ticket_count: 0, sized_count: 0, total_points: 0 }
    try {
      const created = await api.createRoom({ name: roomName, scale: 'fibonacci', reveal_mode: 'manual' })
      setRoom(created)
      setRooms((items) => [created, ...items])
    } catch {
      setRoom(localRoom)
      setRooms((items) => [localRoom, ...items])
    }
    setView('import')
  }

  const startImportedSession = async () => {
    if (!parsedTickets.length) return
    let nextTickets = parsedTickets
    try { nextTickets = await api.importTickets(room.id, parsedTickets) } catch { /* local demo */ }
    setTickets(nextTickets)
    setTicketIndex(0)
    setSelectedVote(null)
    setRevealed(false)
    setView('session')
  }

  const openTicket = (index) => {
    setTicketIndex(index)
    setSelectedVote(null)
    setRevealed(false)
    setView('session')
  }

  const saveEstimate = (points) => {
    const numeric = Number(points)
    setTickets((items) => items.map((item, index) => index === ticketIndex ? { ...item, story_points: numeric } : item))
    api.estimate(current.id, numeric).catch(() => {})
  }

  const exportCsv = () => {
    const escape = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
    const rows = [
      ['Issue key', 'Summary', 'Issue Type', 'Story Points'],
      ...tickets.map((item) => [item.issue_key, item.summary, item.issue_type, item.story_points]),
    ]
    const blob = new Blob([rows.map((row) => row.map(escape).join(',')).join('\n')], { type: 'text/csv' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${room.name.toLowerCase().replaceAll(/[^a-z0-9]+/g, '-')}-estimates.csv`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  const nextTicket = () => {
    setTicketIndex((index) => Math.min(index + 1, tickets.length - 1))
    setSelectedVote(null)
    setRevealed(false)
  }

  if (view === 'rooms') return (
    <Shell status={apiOnline} onRooms={() => setView('rooms')}>
      <main className="page rooms-page">
        <section className="page-heading">
          <div><p className="eyebrow">Workspace / product</p><h1>Pricing rooms</h1><p>Make the work small enough to understand.</p></div>
          <div className="member-stack">{team.slice(0, 3).map((p) => <span key={p.initials}>{p.initials}</span>)}<button>+ Invite</button></div>
        </section>
        <section className="rooms-grid">
          <div className="new-room panel">
            <div className="panel-label"><span>New room</span><small>01</small></div>
            <label>Room name<input value={roomName} onChange={(e) => setRoomName(e.target.value)} /></label>
            <label>Scale<div className="segmented"><button className="active">Fibonacci</button><button>T-shirt</button></div></label>
            <button className="primary wide" onClick={createRoom}>Create pricing room <span>→</span></button>
          </div>
          <div className="room-list">
            <div className="section-kicker"><span>Active rooms</span><small>{String(rooms.length).padStart(2, '0')}</small></div>
            {rooms.map((item) => <button className="room-card" key={item.id} onClick={() => loadRoom(item)}>
              <div className="room-card-top"><div><small>PLANNING</small><h2>{item.name}</h2></div><span className="arrow">↗</span></div>
              <div className="progress"><i style={{ width: `${item.ticket_count ? (item.sized_count / item.ticket_count) * 100 : 0}%` }} /></div>
              <div className="room-meta"><span>{item.sized_count} / {item.ticket_count} sized</span><span>{item.total_points} pts</span></div>
            </button>)}
          </div>
        </section>
      </main>
    </Shell>
  )

  if (view === 'import') return (
    <Shell status={apiOnline} onRooms={() => setView('rooms')}>
      <main className="page import-page">
        <Back onClick={() => setView('rooms')}>Rooms</Back>
        <div className="split-heading"><div><p className="eyebrow">{room.name} / import</p><h1>Bring in the tickets.</h1></div><p>Paste a Jira export. We’ll keep the key, type and story context attached to every estimate.</p></div>
        <section className="import-grid">
          <div className="panel import-editor"><div className="panel-label"><span>CSV input</span><small>01</small></div><textarea value={importText} onChange={(e) => setImportText(e.target.value)} /><div className="editor-actions"><label className="secondary file-picker">Choose file<input type="file" accept=".csv,.tsv,.txt" onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; const reader = new FileReader(); reader.onload = () => setImportText(String(reader.result || '')); reader.readAsText(file) }} /></label><span>CSV, TSV or plain text</span></div></div>
          <div className="panel preview"><div className="panel-label"><span>Preview</span><small>{String(parsedTickets.length).padStart(2, '0')}</small></div>{parsedTickets.map((item) => <div className="preview-row" key={item.id}><span>{item.issue_key}</span><p>{item.summary}</p><small>{item.issue_type}</small></div>)}<button className="primary wide" disabled={!parsedTickets.length} onClick={startImportedSession}>Start session <span>→</span></button></div>
        </section>
      </main>
    </Shell>
  )

  if (view === 'backlog') return (
    <Shell status={apiOnline} onRooms={() => setView('rooms')}>
      <main className="page backlog-page">
        <Back onClick={() => setView('rooms')}>Rooms</Back>
        <section className="page-heading"><div><p className="eyebrow">{room.name}</p><h1>Backlog</h1><p>{completion}% priced · {tickets.filter((t) => t.story_points == null).length} stories need a conversation</p></div><button className="primary" disabled={nextUnsizedIndex < 0} onClick={() => openTicket(nextUnsizedIndex)}>Price next story <span>→</span></button></section>
        <div className="ticket-table panel"><div className="ticket-row ticket-head"><span>Key</span><span>Summary</span><span>Type</span><span>Points</span></div>{tickets.map((item, index) => <button className="ticket-row" key={item.id} onClick={() => openTicket(index)}><span>{item.issue_key}</span><strong>{item.summary}</strong><small>{item.issue_type}</small><b className={item.story_points == null ? 'empty-points' : ''}>{item.story_points ?? '—'}</b></button>)}</div>
      </main>
    </Shell>
  )

  if (view === 'summary') return (
    <Shell status={apiOnline} onRooms={() => setView('rooms')}>
      <main className="page summary-page"><Back onClick={() => setView('session')}>Session</Back><section className="page-heading"><div><p className="eyebrow">{room.name}</p><h1>Pricing summary</h1></div><button className="secondary" onClick={exportCsv}>Export CSV ↓</button></section><div className="summary-stats"><div><strong>{tickets.reduce((sum, item) => sum + (item.story_points || 0), 0)}</strong><span>Total points</span></div><div><strong>{tickets.filter((item) => item.story_points != null).length}</strong><span>Stories sized</span></div><div><strong>{completion}%</strong><span>Complete</span></div></div><div className="ticket-table panel">{tickets.map((item, index) => <button className="ticket-row" key={item.id} onClick={() => openTicket(index)}><span>{item.issue_key}</span><strong>{item.summary}</strong><small>{item.issue_type}</small><b className={item.story_points == null ? 'empty-points' : ''}>{item.story_points ?? '—'}</b></button>)}</div></main>
    </Shell>
  )

  return (
    <div className="session-shell">
      <header className="session-top"><Back onClick={() => setView('backlog')}>Backlog</Back><div><strong>{room.name}</strong><span>{ticketIndex + 1} of {tickets.length}</span></div><div className="session-actions"><button onClick={() => setShowDetail((value) => !value)}>{showDetail ? 'Hide' : 'Ticket'} detail</button><button onClick={() => setView('summary')}>Summary</button></div></header>
      <main className="session-main">
        <section className="story-copy"><p className="eyebrow">{current?.issue_key} · {current?.issue_type}</p><h1>{current?.summary}</h1>{showDetail && <p className="description">{current?.description || 'No ticket description supplied.'}</p>}</section>
        <section className="vote-area"><p className="micro-label">Choose your estimate</p><div className="cards">{scale.map((value) => <button key={value} className={selectedVote === value ? 'selected' : ''} onClick={() => { setSelectedVote(value); setRevealed(false) }}>{value}</button>)}</div></section>
        {!revealed ? <section className="waiting"><div className="avatars">{team.map((person, index) => <span className={index === 0 && selectedVote ? 'voted' : index > 0 ? 'voted' : ''} key={person.initials}>{person.initials}</span>)}</div><p>{selectedVote ? '4 of 4 voted' : '3 of 4 voted · waiting for you'}</p><button className="reveal" disabled={!selectedVote} onClick={() => setRevealed(true)}>Reveal cards</button></section> : <Results selected={selectedVote} onEstimate={saveEstimate} onNext={nextTicket} onRevote={() => setRevealed(false)} />}
      </main>
      <footer className="ticket-rail"><button onClick={() => openTicket(Math.max(0, ticketIndex - 1))}>←</button><div>{tickets.map((item, index) => <button key={item.id} className={index === ticketIndex ? 'active' : item.story_points != null ? 'done' : ''} onClick={() => openTicket(index)}>{String(index + 1).padStart(2, '0')}</button>)}</div><button onClick={nextTicket}>→</button></footer>
    </div>
  )
}

function Results({ selected, onEstimate, onNext, onRevote }) {
  const [finalEstimate, setFinalEstimate] = useState(!Number.isNaN(Number(selected)) ? selected : '5')
  const votes = [selected, '5', '8', '5']
  return <section className="results"><div className="result-cards">{team.map((person, index) => <div key={person.initials}><strong>{votes[index]}</strong><span>{person.name}</span></div>)}</div><div className="consensus"><div><strong>5.8</strong><span>Average</span></div><div><strong>5–8</strong><span>Range</span></div><div><strong className="good">Close</strong><span>Consensus</span></div></div><div className="final-estimate"><p className="micro-label">Set final estimate</p><div>{['0', '1', '2', '3', '5', '8', '13', '21'].map((point) => <button className={finalEstimate === point ? 'active' : ''} key={point} onClick={() => setFinalEstimate(point)}>{point}</button>)}</div></div><div className="result-actions"><button className="secondary" onClick={onRevote}>Re-vote</button><button className="primary" onClick={() => { onEstimate(finalEstimate); onNext() }}>Save & next <span>→</span></button></div></section>
}

function Back({ children, onClick }) { return <button className="back" onClick={onClick}>← {children}</button> }

function Shell({ children, status, onRooms }) {
  return <div><header className="app-header"><Logo /><nav><button onClick={onRooms}>Rooms</button><button disabled>People</button><button className="avatar">TP</button></nav></header>{children}<footer className="app-footer"><Logo /><span><i className={status ? 'online' : ''} /> {status ? 'API connected' : 'Demo mode'}</span></footer></div>
}

export default App
