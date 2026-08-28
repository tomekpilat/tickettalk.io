import { useCallback, useEffect, useState } from 'react'
import { sendMagicLink, signInAsMember, signOut, useAuth } from './lib/auth.js'
import { api } from './lib/api.js'
import { isRoomLikePath, pushPath, roomIdFromPath, roomPath } from './lib/routing.js'
import { subscribeToRoom } from './lib/supabase.js'

const scales = {
  fibonacci: ['0', '1', '2', '3', '5', '8', '13', '21', '?'],
  extended: ['1', '2', '3', '5', '8', '13', '21', '34', '55', '?'],
  tshirt: ['XS', 'S', 'M', 'L', 'XL', '?'],
}

const scaleChoices = [
  { value: 'fibonacci', label: 'Fibonacci', hint: '0 · 1 · 2 · 3 · 5 · 8 · 13 · 21' },
  { value: 'extended', label: 'Extended', hint: '1 · 2 · 3 · 5 · 8 · 13 · 21 · 34 · 55' },
  { value: 'tshirt', label: 'T-shirt', hint: 'XS · S · M · L · XL' },
]

const team = [
  { name: 'You', initials: 'TP' },
  { name: 'Maya', initials: 'MO' },
  { name: 'Alex', initials: 'AK' },
  { name: 'Jo', initials: 'JL' },
]

const sampleImport = 'Issue key,Summary,Issue Type\nPAY-201,Add wallet balance alert,Story\nPAY-205,Fix duplicate webhook delivery,Bug'
const emptyTicketDraft = { issue_key: '', summary: '', issue_type: 'Story', description: '' }

function Logo() {
  return <div className="logo"><span>ticket<strong>talks.</strong></span></div>
}

function initials(name) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || 'TT'
}

function App() {
  const auth = useAuth()
  const [joiningRoomId, setJoiningRoomId] = useState(null)
  const sharedRoomId = roomIdFromPath()
  if (auth.loading) return <CenteredState eyebrow="Session" title="Checking your session…" />
  if (auth.error) return <CenteredState eyebrow="Configuration" title="The app needs attention." detail={auth.error} />
  if ((!auth.user || joiningRoomId === sharedRoomId) && sharedRoomId) return (
    <JoinRoom
      roomId={sharedRoomId}
      hasAnonymousSession={Boolean(auth.user?.isAnonymous)}
      onJoining={() => setJoiningRoomId(sharedRoomId)}
      onJoined={() => setJoiningRoomId(null)}
    />
  )
  if (!auth.user && isRoomLikePath()) return <CenteredState eyebrow="Room access" title="Room link not recognized." detail="Check the URL and ask the facilitator for a new link." />
  if (!auth.user) return <SignIn />
  return <Workspace user={auth.user} />
}

function Workspace({ user }) {
  const [view, setView] = useState('rooms')
  const [rooms, setRooms] = useState([])
  const [room, setRoom] = useState(null)
  const [members, setMembers] = useState([])
  const [tickets, setTickets] = useState([])
  const [ticketIndex, setTicketIndex] = useState(0)
  const [selectedVote, setSelectedVote] = useState(null)
  const [revealed, setRevealed] = useState(false)
  const [showDetail, setShowDetail] = useState(false)
  const [roomName, setRoomName] = useState('Sprint 43 planning')
  const [roomScale, setRoomScale] = useState('fibonacci')
  const [revealMode, setRevealMode] = useState('manual')
  const [importText, setImportText] = useState(sampleImport)
  const [duplicateBehavior, setDuplicateBehavior] = useState('error')
  const [importPreview, setImportPreview] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [ticketDraft, setTicketDraft] = useState(null)
  const [editingTicketId, setEditingTicketId] = useState(null)
  const [apiOnline, setApiOnline] = useState(false)
  const [loading, setLoading] = useState(true)
  const [formError, setFormError] = useState('')
  const [routeError, setRouteError] = useState(null)
  const [creating, setCreating] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsDraft, setSettingsDraft] = useState(null)
  const [toast, setToast] = useState('')

  const refreshRooms = useCallback(async () => {
    try {
      const data = await api.rooms()
      setRooms(data)
      setApiOnline(true)
      return data
    } catch (error) {
      setApiOnline(false)
      setRouteError({ title: 'Rooms are unavailable.', detail: error.message })
      return []
    }
  }, [])

  const refreshMembers = useCallback(async (roomId) => {
    const nextMembers = await api.members(roomId)
    setMembers(nextMembers)
    return nextMembers
  }, [])

  const openRoom = useCallback(async (roomId, options = {}) => {
    setLoading(true)
    setRouteError(null)
    try {
      const [nextRoom, nextTickets, nextMembers] = await Promise.all([
        api.room(roomId),
        api.tickets(roomId),
        api.members(roomId),
      ])
      setRoom(nextRoom)
      setTickets(nextTickets)
      setMembers(nextMembers)
      setTicketIndex(Math.max(0, nextTickets.findIndex((ticket) => ticket.id === nextRoom.active_ticket_id)))
      setView(nextTickets.length ? 'backlog' : 'import')
      setApiOnline(true)
      if (options.push !== false) pushPath(roomPath(nextRoom.id))
    } catch (error) {
      const title = error.status === 403 ? 'This room is private.' : 'Room not found.'
      setRouteError({ title, detail: error.message, status: error.status })
      setView('route-error')
      setMembers([])
      setApiOnline(error.status !== undefined)
    } finally {
      setLoading(false)
    }
  }, [])

  const goToRooms = useCallback(() => {
    pushPath('/')
    setView('rooms')
    setRoom(null)
    setTickets([])
    setMembers([])
    setRouteError(null)
    setSettingsOpen(false)
    refreshRooms()
  }, [refreshRooms])

  useEffect(() => {
    const resolveLocation = () => {
      const roomId = roomIdFromPath()
      if (roomId) {
        openRoom(roomId, { push: false })
      } else if (isRoomLikePath()) {
        setRouteError({ title: 'Room link not recognized.', detail: 'Check the URL and ask the facilitator for a new link.' })
        setView('route-error')
        setLoading(false)
      } else {
        setView('rooms')
        setLoading(true)
        refreshRooms().finally(() => setLoading(false))
      }
    }
    resolveLocation()
    window.addEventListener('popstate', resolveLocation)
    return () => window.removeEventListener('popstate', resolveLocation)
  }, [openRoom, refreshRooms])

  useEffect(() => {
    if (!room?.id) return undefined
    return subscribeToRoom(room.id, async () => {
      try {
        const [freshRoom, freshTickets, freshMembers] = await Promise.all([
          api.room(room.id), api.tickets(room.id), api.members(room.id),
        ])
        setRoom(freshRoom)
        setTickets(freshTickets)
        setMembers(freshMembers)
      } catch { /* the next user action will surface connectivity or authorization */ }
    })
  }, [room?.id])

  useEffect(() => {
    if (!room?.id) return undefined
    const heartbeat = async () => {
      try {
        await api.touchPresence(room.id)
        await refreshMembers(room.id)
      } catch { /* presence retries on the next heartbeat */ }
    }
    heartbeat()
    const interval = window.setInterval(heartbeat, 15000)
    return () => window.clearInterval(interval)
  }, [refreshMembers, room?.id])

  useEffect(() => {
    if (!toast) return undefined
    const timeout = window.setTimeout(() => setToast(''), 2400)
    return () => window.clearTimeout(timeout)
  }, [toast])

  const current = tickets[ticketIndex] || tickets[0]
  const completion = tickets.length
    ? Math.round((tickets.filter((item) => item.story_points != null).length / tickets.length) * 100)
    : 0
  const nextUnsizedIndex = tickets.findIndex((item) => item.story_points == null)
  const votingScale = scales[room?.scale] || scales.fibonacci
  const isFacilitator = Boolean(room && room.owner_id === user.id)

  useEffect(() => {
    if (!room?.id || view !== 'import' || !isFacilitator || !importText.trim()) {
      setImportPreview(null)
      return undefined
    }
    let cancelled = false
    setPreviewing(true)
    const timeout = window.setTimeout(async () => {
      try {
        const preview = await api.previewImport(room.id, importText, duplicateBehavior)
        if (!cancelled) setImportPreview(preview)
      } catch (error) {
        if (!cancelled) {
          setImportPreview(null)
          setFormError(error.message)
        }
      } finally {
        if (!cancelled) setPreviewing(false)
      }
    }, 250)
    return () => {
      cancelled = true
      window.clearTimeout(timeout)
    }
  }, [duplicateBehavior, importText, isFacilitator, room?.id, view])

  const createRoom = async () => {
    setFormError('')
    if (roomName.trim().length < 3) {
      setFormError('Room name needs at least 3 characters.')
      return
    }
    setCreating(true)
    try {
      const created = await api.createRoom({
        name: roomName,
        scale: roomScale,
        reveal_mode: revealMode,
      })
      setRoom(created)
      setRooms((items) => [created, ...items])
      setTickets([])
      pushPath(roomPath(created.id))
      setView('import')
      setApiOnline(true)
    } catch (error) {
      setFormError(error.message)
    } finally {
      setCreating(false)
    }
  }

  const saveImport = async () => {
    if (!importPreview?.saved_count || importPreview.errors.length || !room) return
    setImporting(true)
    setFormError('')
    try {
      const result = await api.importTickets(room.id, importText, duplicateBehavior)
      setTickets(result.tickets)
      setRoom((currentRoom) => ({ ...currentRoom, ticket_count: result.tickets.length }))
      setToast(`${result.imported_count + result.replaced_count} tickets saved`)
      setView('backlog')
    } catch (error) {
      setFormError(error.message)
    } finally {
      setImporting(false)
    }
  }

  const loadImportFile = (file) => {
    if (!file) return
    if (file.size > 1_000_000) {
      setFormError('The import is larger than 1 MB. Split it into smaller files.')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      setFormError('')
      setImportText(String(reader.result || ''))
    }
    reader.readAsText(file)
  }

  const openNewTicket = () => {
    setEditingTicketId(null)
    setTicketDraft({ ...emptyTicketDraft })
    setFormError('')
  }

  const openTicketEditor = (ticket) => {
    setEditingTicketId(ticket.id)
    setTicketDraft({
      issue_key: ticket.issue_key || '',
      summary: ticket.summary,
      issue_type: ticket.issue_type,
      description: ticket.description || '',
    })
    setFormError('')
  }

  const saveTicketDraft = async () => {
    if (!ticketDraft?.summary.trim()) {
      setFormError('Ticket summary is required.')
      return
    }
    const payload = {
      ...ticketDraft,
      issue_key: ticketDraft.issue_key.trim() || null,
    }
    try {
      if (editingTicketId) {
        const updated = await api.updateTicket(room.id, editingTicketId, payload)
        setTickets((items) => items.map((item) => item.id === updated.id ? updated : item))
        setToast('Ticket updated')
      } else {
        const created = await api.createTicket(room.id, payload)
        setTickets((items) => [...items, created])
        setRoom((currentRoom) => ({ ...currentRoom, ticket_count: currentRoom.ticket_count + 1 }))
        setView('backlog')
        setToast('Ticket added')
      }
      setTicketDraft(null)
      setEditingTicketId(null)
    } catch (error) {
      setFormError(error.message)
    }
  }

  const deleteBacklogTicket = async (ticket) => {
    if (!window.confirm(`Remove ${ticket.issue_key || ticket.summary} from this room?`)) return
    try {
      await api.deleteTicket(room.id, ticket.id)
      const remaining = tickets.filter((item) => item.id !== ticket.id)
        .map((item, position) => ({ ...item, position }))
      setTickets(remaining)
      setRoom((currentRoom) => ({ ...currentRoom, ticket_count: remaining.length }))
      setToast('Ticket removed')
      if (!remaining.length) setView('import')
    } catch (error) {
      setToast(error.message)
    }
  }

  const moveBacklogTicket = async (index, direction) => {
    const destination = index + direction
    if (destination < 0 || destination >= tickets.length) return
    const reordered = [...tickets]
    const [moved] = reordered.splice(index, 1)
    reordered.splice(destination, 0, moved)
    try {
      const persisted = await api.reorderTickets(room.id, reordered.map((ticket) => ticket.id))
      setTickets(persisted)
    } catch (error) {
      setToast(error.message)
    }
  }

  const openTicket = (index) => {
    if (index < 0 || index >= tickets.length) return
    setTicketIndex(index)
    setSelectedVote(null)
    setRevealed(false)
    setView('session')
  }

  const saveEstimate = async (points) => {
    const numeric = Number(points)
    setTickets((items) => items.map((item, index) => (
      index === ticketIndex ? { ...item, story_points: numeric } : item
    )))
    try { await api.estimate(current.id, numeric) } catch (error) { setToast(error.message) }
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

  const shareRoom = async () => {
    const url = `${window.location.origin}${roomPath(room.id)}`
    try {
      await navigator.clipboard.writeText(url)
      setToast('Room link copied')
    } catch {
      window.prompt('Copy this room link', url)
    }
  }

  const openSettings = () => {
    setSettingsDraft({
      name: room.name,
      scale: room.scale,
      reveal_mode: room.reveal_mode,
    })
    setFormError('')
    setSettingsOpen(true)
  }

  const saveSettings = async () => {
    setFormError('')
    try {
      const updated = await api.updateRoom(room.id, settingsDraft)
      setRoom(updated)
      setRooms((items) => items.map((item) => item.id === updated.id ? updated : item))
      setSettingsOpen(false)
      setToast('Room settings saved')
    } catch (error) {
      setFormError(error.message)
    }
  }

  const roomActions = room && isFacilitator ? (
    <div className="room-actions">
      <button className="secondary" onClick={shareRoom}>Copy room link</button>
      <button className="secondary" onClick={openSettings}>Room settings</button>
    </div>
  ) : null

  if (loading) return <CenteredState eyebrow="Room" title="Loading the room…" />

  if (view === 'route-error' && routeError?.status === 403 && user.isAnonymous) return (
    <JoinRoom
      roomId={roomIdFromPath()}
      hasAnonymousSession
      defaultName={user.displayName}
      onJoined={() => openRoom(roomIdFromPath(), { push: false })}
    />
  )

  if (view === 'route-error') return (
    <Shell status={apiOnline} user={user} onRooms={goToRooms}>
      <CenteredState eyebrow="Room access" title={routeError?.title || 'Room unavailable.'} detail={routeError?.detail} action={<button className="primary" onClick={goToRooms}>Back to rooms</button>} />
    </Shell>
  )

  if (view === 'rooms') return (
    <Shell status={apiOnline} user={user} onRooms={goToRooms}>
      <main className="page rooms-page">
        <section className="page-heading">
          <div><p className="eyebrow">Workspace / product</p><h1>Pricing rooms</h1><p>Make the work small enough to understand.</p></div>
          <div className="account-caption"><span>{user.displayName}</span><small>Facilitator</small></div>
        </section>
        <section className="rooms-grid">
          <div className="new-room panel">
            <div className="panel-label"><span>New room</span><small>01</small></div>
            <label>Room name<input value={roomName} onChange={(event) => setRoomName(event.target.value)} maxLength={120} /></label>
            <fieldset className="choice-field"><legend>Scale</legend>{scaleChoices.map((choice) => <button key={choice.value} className={roomScale === choice.value ? 'choice active' : 'choice'} onClick={() => setRoomScale(choice.value)}><strong>{choice.label}</strong><small>{choice.hint}</small></button>)}</fieldset>
            <fieldset className="choice-field"><legend>Reveal</legend><div className="segmented"><button className={revealMode === 'manual' ? 'active' : ''} onClick={() => setRevealMode('manual')}>Manual</button><button className={revealMode === 'auto' ? 'active' : ''} onClick={() => setRevealMode('auto')}>When all voted</button></div></fieldset>
            {formError && <p className="form-error">{formError}</p>}
            <button className="primary wide" disabled={creating} onClick={createRoom}>{creating ? 'Creating room…' : 'Create pricing room'} <span>→</span></button>
          </div>
          <div className="room-list">
            <div className="section-kicker"><span>Active rooms</span><small>{String(rooms.length).padStart(2, '0')}</small></div>
            {!rooms.length && <div className="empty-state">No rooms yet. Create the first pricing room.</div>}
            {rooms.map((item) => <button className="room-card" key={item.id} onClick={() => openRoom(item.id)}>
              <div className="room-card-top"><div><small>{item.scale}</small><h2>{item.name}</h2></div><span className="arrow">↗</span></div>
              <div className="progress"><i style={{ width: `${item.ticket_count ? (item.sized_count / item.ticket_count) * 100 : 0}%` }} /></div>
              <div className="room-meta"><span>{item.sized_count} / {item.ticket_count} sized</span><span>{item.total_points} pts</span></div>
            </button>)}
          </div>
        </section>
      </main>
    </Shell>
  )

  if (view === 'import' && !isFacilitator) return (
    <Shell status={apiOnline} user={user} onRooms={goToRooms}>
      <main className="page member-lobby">
        <div className="page-toolbar"><Back onClick={goToRooms}>Rooms</Back></div>
        <section className="page-heading"><div><p className="eyebrow">{room.name}</p><h1>You’re in.</h1><p>The facilitator is preparing the tickets. Keep this tab open and the room will update automatically.</p></div></section>
        <ParticipantRoster members={members} currentUserId={user.id} />
      </main>
    </Shell>
  )

  if (view === 'import') return (
    <Shell status={apiOnline} user={user} onRooms={goToRooms}>
      <main className="page import-page">
        <div className="page-toolbar"><Back onClick={goToRooms}>Rooms</Back>{roomActions}</div>
        <div className="split-heading"><div><p className="eyebrow">{room.name} / import</p><h1>Bring in the tickets.</h1></div><p>Paste a Jira export. We’ll keep the key, type and story context attached to every estimate.</p></div>
        <ParticipantRoster members={members} currentUserId={user.id} compact />
        {formError && <p className="form-error inline-error">{formError}</p>}
        <section className="import-grid">
          <div className="panel import-editor"><div className="panel-label"><span>CSV or TSV input</span><small>01</small></div><textarea aria-label="Jira import" value={importText} onChange={(event) => setImportText(event.target.value)} /><label className="duplicate-choice">Existing Jira keys<select value={duplicateBehavior} onChange={(event) => setDuplicateBehavior(event.target.value)}><option value="error">Ask me to decide</option><option value="skip">Skip existing</option><option value="replace">Replace existing</option></select></label><div className="editor-actions"><label className="secondary file-picker">Choose file<input type="file" accept=".csv,.tsv,.txt" onChange={(event) => loadImportFile(event.target.files?.[0])} /></label><span>Maximum 1 MB · 500 tickets</span></div></div>
          <div className="panel preview"><div className="panel-label"><span>Validated preview</span><small>{String(importPreview?.source_count || 0).padStart(2, '0')}</small></div>{previewing && <p className="preview-message">Checking rows…</p>}{importPreview?.errors.map((error) => <div className="import-error" key={`${error.row_number}-${error.field}`}><strong>Row {error.row_number || '—'} · {error.field}</strong><span>{error.message}</span><small>{error.fix}</small></div>)}{!previewing && importPreview?.rows.map((item) => <div className="preview-row" key={`${item.row_number}-${item.issue_key || item.summary}`}><span>{item.issue_key || 'Manual'}</span><p>{item.summary}</p><small>{item.action}</small></div>)}<div className="preview-counts"><span>{importPreview?.saved_count || 0} to save</span><span>{importPreview?.skipped_count || 0} skipped</span></div><button className="primary wide" disabled={previewing || importing || !importPreview?.saved_count || importPreview.errors.length > 0} onClick={saveImport}>{importing ? 'Saving tickets…' : `Save ${importPreview?.saved_count || 0} to backlog`} <span>→</span></button></div>
        </section>
        <div className="manual-entry"><span>Not in Jira?</span><button className="secondary" onClick={openNewTicket}>Add a ticket manually</button></div>
      </main>
      {settingsOpen && <RoomSettings room={room} draft={settingsDraft} setDraft={setSettingsDraft} ticketCount={tickets.length} error={formError} onClose={() => setSettingsOpen(false)} onSave={saveSettings} />}
      {ticketDraft && <TicketEditor draft={ticketDraft} setDraft={setTicketDraft} editing={Boolean(editingTicketId)} error={formError} onClose={() => setTicketDraft(null)} onSave={saveTicketDraft} />}
      {toast && <Toast>{toast}</Toast>}
    </Shell>
  )

  if (view === 'backlog') return (
    <Shell status={apiOnline} user={user} onRooms={goToRooms}>
      <main className="page backlog-page">
        <div className="page-toolbar"><Back onClick={goToRooms}>Rooms</Back>{roomActions}</div>
        <section className="page-heading"><div><p className="eyebrow">{room.name}</p><h1>Backlog</h1><p>{completion}% priced · {tickets.filter((ticket) => ticket.story_points == null).length} tickets need a conversation</p></div>{isFacilitator && <div className="heading-actions"><button className="secondary" onClick={openNewTicket}>Add ticket</button><button className="primary" disabled={nextUnsizedIndex < 0} onClick={() => openTicket(nextUnsizedIndex)}>Price next ticket <span>→</span></button></div>}</section>
        <ParticipantRoster members={members} currentUserId={user.id} compact />
        <BacklogTable tickets={tickets} isFacilitator={isFacilitator} onOpen={openTicket} onEdit={openTicketEditor} onDelete={deleteBacklogTicket} onMove={moveBacklogTicket} />
      </main>
      {settingsOpen && <RoomSettings room={room} draft={settingsDraft} setDraft={setSettingsDraft} ticketCount={tickets.length} error={formError} onClose={() => setSettingsOpen(false)} onSave={saveSettings} />}
      {ticketDraft && <TicketEditor draft={ticketDraft} setDraft={setTicketDraft} editing={Boolean(editingTicketId)} error={formError} onClose={() => setTicketDraft(null)} onSave={saveTicketDraft} />}
      {toast && <Toast>{toast}</Toast>}
    </Shell>
  )

  if (view === 'summary') return (
    <Shell status={apiOnline} user={user} onRooms={goToRooms}>
      <main className="page summary-page"><div className="page-toolbar"><Back onClick={() => setView('session')}>Session</Back>{roomActions}</div><section className="page-heading"><div><p className="eyebrow">{room.name}</p><h1>Pricing summary</h1></div>{isFacilitator && <button className="secondary" onClick={exportCsv}>Export CSV ↓</button>}</section><ParticipantRoster members={members} currentUserId={user.id} compact /><div className="summary-stats"><div><strong>{tickets.reduce((sum, item) => sum + (item.story_points || 0), 0)}</strong><span>Total points</span></div><div><strong>{tickets.filter((item) => item.story_points != null).length}</strong><span>Tickets sized</span></div><div><strong>{completion}%</strong><span>Complete</span></div></div><div className="ticket-table panel">{tickets.map((item, index) => <button className="ticket-row" key={item.id} onClick={() => openTicket(index)}><span>{item.issue_key}</span><strong>{item.summary}</strong><small>{item.issue_type}</small><b className={item.story_points == null ? 'empty-points' : ''}>{item.story_points ?? '—'}</b></button>)}</div></main>
      {settingsOpen && <RoomSettings room={room} draft={settingsDraft} setDraft={setSettingsDraft} ticketCount={tickets.length} error={formError} onClose={() => setSettingsOpen(false)} onSave={saveSettings} />}
      {toast && <Toast>{toast}</Toast>}
    </Shell>
  )

  return (
    <div className="session-shell">
      <header className="session-top"><Back onClick={() => setView('backlog')}>Backlog</Back><div><strong>{room.name}</strong><span>{ticketIndex + 1} of {tickets.length}</span></div><div className="session-actions">{isFacilitator && <button onClick={shareRoom}>Share</button>}<button onClick={() => setShowDetail((value) => !value)}>{showDetail ? 'Hide' : 'Ticket'} detail</button><button onClick={() => setView('summary')}>Summary</button></div></header>
      <main className="session-main">
        <ParticipantRoster members={members} currentUserId={user.id} compact />
        <section className="story-copy"><p className="eyebrow">{current?.issue_key} · {current?.issue_type}</p><h1>{current?.summary}</h1>{showDetail && <p className="description">{current?.description || 'No ticket description supplied.'}</p>}</section>
        <section className="vote-area"><p className="micro-label">Choose your estimate</p><div className="cards">{votingScale.map((value) => <button key={value} className={selectedVote === value ? 'selected' : ''} onClick={() => { setSelectedVote(value); setRevealed(false) }}>{value}</button>)}</div></section>
        {!revealed ? <section className="waiting"><div className="avatars">{team.map((person, index) => <span className={index === 0 && selectedVote ? 'voted' : index > 0 ? 'voted' : ''} key={person.initials}>{person.initials}</span>)}</div><p>{selectedVote ? '4 of 4 voted' : '3 of 4 voted · waiting for you'}</p><button className="reveal" disabled={!selectedVote} onClick={() => setRevealed(true)}>Reveal cards</button></section> : <Results selected={selectedVote} onEstimate={saveEstimate} onNext={nextTicket} onRevote={() => setRevealed(false)} />}
      </main>
      <footer className="ticket-rail"><button onClick={() => openTicket(Math.max(0, ticketIndex - 1))}>←</button><div>{tickets.map((item, index) => <button key={item.id} className={index === ticketIndex ? 'active' : item.story_points != null ? 'done' : ''} onClick={() => openTicket(index)}>{String(index + 1).padStart(2, '0')}</button>)}</div><button onClick={nextTicket}>→</button></footer>
      {toast && <Toast>{toast}</Toast>}
    </div>
  )
}

function JoinRoom({ roomId, hasAnonymousSession = false, defaultName = '', onJoining, onJoined }) {
  const [displayName, setDisplayName] = useState(defaultName)
  const [message, setMessage] = useState('')
  const [joining, setJoining] = useState(false)
  const [joined, setJoined] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    const normalizedName = displayName.trim().replace(/\s+/g, ' ')
    if (!normalizedName) {
      setMessage('Enter your name to join.')
      return
    }
    setJoining(true)
    setMessage('')
    onJoining?.()
    try {
      if (!hasAnonymousSession) await signInAsMember(normalizedName)
      await api.joinRoom(roomId, normalizedName)
      setJoined(true)
      onJoined?.()
    } catch (error) {
      setMessage(error.status === 403 || error.status === 404
        ? 'This room is unavailable. Ask the facilitator for a new link.'
        : error.message)
    } finally {
      setJoining(false)
    }
  }

  if (joined) return <CenteredState eyebrow="Room access" title="You’re in." detail="Loading the pricing room…" />

  return <div className="auth-page"><Logo /><form className="auth-panel panel" onSubmit={submit}><p className="eyebrow">Shared pricing room</p><h1>Join the conversation.</h1><p>Enter the name your teammates will recognize. No account or password is required.</p><label>Your name<input autoFocus required maxLength={80} value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="e.g. Maya" /></label>{message && <p className="auth-message form-error">{message}</p>}<button className="primary wide" disabled={joining}>{joining ? 'Joining room…' : 'Join room'} <span>→</span></button><small className="privacy-note">Your browser keeps a private session so refreshing will not add you twice.</small></form></div>
}

function ParticipantRoster({ members, currentUserId, compact = false }) {
  return <section className={compact ? 'participant-roster compact' : 'participant-roster panel'} aria-label="Participants"><div className="roster-heading"><span>Participants</span><small>{members.filter((member) => member.is_online).length} online · {members.length} joined</small></div><div className="roster-list">{members.map((member) => {
    const status = member.has_voted ? 'Voted' : member.is_online ? 'Joined' : 'Disconnected'
    return <div className="roster-person" key={member.user_id}><span className={member.is_online ? 'roster-avatar online' : 'roster-avatar'}>{initials(member.display_name)}</span><span><strong>{member.user_id === currentUserId ? `${member.display_name} (you)` : member.display_name}</strong><small>{member.role === 'facilitator' ? 'Facilitator' : status}</small></span><i className={member.has_voted ? 'member-status voted' : member.is_online ? 'member-status' : 'member-status offline'} aria-label={status} /></div>
  })}</div></section>
}

function SignIn() {
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setSending(true)
    setMessage('')
    try {
      await sendMagicLink(email)
      setMessage('Check your email for the sign-in link.')
    } catch (error) {
      setMessage(error.message)
    } finally {
      setSending(false)
    }
  }

  return <div className="auth-page"><Logo /><form className="auth-panel panel" onSubmit={submit}><p className="eyebrow">Facilitator access</p><h1>Sign in to create a room.</h1><p>We’ll email you a secure sign-in link. Team members join separately through the room URL.</p><label>Work email<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" /></label>{message && <p className="auth-message">{message}</p>}<button className="primary wide" disabled={sending}>{sending ? 'Sending link…' : 'Email me a sign-in link'} <span>→</span></button></form></div>
}

function BacklogTable({ tickets, isFacilitator, onOpen, onEdit, onDelete, onMove }) {
  return <div className="ticket-table panel"><div className="ticket-row ticket-head"><span>Key</span><span>Summary</span><span>Type</span><span>Points</span></div>{tickets.map((item, index) => <div className="backlog-row" key={item.id}><button className="ticket-row ticket-open" onClick={() => onOpen(index)}><span>{item.issue_key || 'Manual'}</span><strong>{item.summary}</strong><small>{item.issue_type}</small><b className={item.story_points == null ? 'empty-points' : ''}>{item.story_points ?? '—'}</b></button>{isFacilitator && <div className="ticket-actions"><button disabled={index === 0} onClick={() => onMove(index, -1)} aria-label={`Move ${item.summary} up`}>↑</button><button disabled={index === tickets.length - 1} onClick={() => onMove(index, 1)} aria-label={`Move ${item.summary} down`}>↓</button><button onClick={() => onEdit(item)} aria-label={`Edit ${item.summary}`}>Edit</button><button className="danger-text" onClick={() => onDelete(item)} aria-label={`Remove ${item.summary}`}>Remove</button></div>}</div>)}</div>
}

function TicketEditor({ draft, setDraft, editing, error, onClose, onSave }) {
  const submit = (event) => {
    event.preventDefault()
    onSave()
  }
  return <div className="modal-backdrop" role="presentation"><form className="settings-panel ticket-editor panel" role="dialog" aria-modal="true" aria-labelledby="ticket-editor-title" onSubmit={submit}><div className="panel-label"><span id="ticket-editor-title">{editing ? 'Edit ticket' : 'Add ticket'}</span><button type="button" onClick={onClose} aria-label="Close ticket editor">×</button></div><label>Issue key <small>Optional</small><input value={draft.issue_key} maxLength={40} onChange={(event) => setDraft({ ...draft, issue_key: event.target.value })} placeholder="PAY-123" /></label><label>Summary<input required value={draft.summary} maxLength={500} onChange={(event) => setDraft({ ...draft, summary: event.target.value })} /></label><label>Type<input required value={draft.issue_type} maxLength={80} onChange={(event) => setDraft({ ...draft, issue_type: event.target.value })} /></label><label>Description<textarea value={draft.description} maxLength={20000} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>{error && <p className="form-error">{error}</p>}<div className="modal-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button className="primary">{editing ? 'Save changes' : 'Add to backlog'}</button></div></form></div>
}

function RoomSettings({ draft, setDraft, ticketCount, error, onClose, onSave }) {
  const locked = ticketCount > 0
  return <div className="modal-backdrop" role="presentation"><section className="settings-panel panel" role="dialog" aria-modal="true" aria-labelledby="room-settings-title"><div className="panel-label"><span id="room-settings-title">Room settings</span><button onClick={onClose} aria-label="Close settings">×</button></div><label>Room name<input value={draft.name} maxLength={120} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label><label>Scale<select value={draft.scale} disabled={locked} onChange={(event) => setDraft({ ...draft, scale: event.target.value })}>{scaleChoices.map((choice) => <option value={choice.value} key={choice.value}>{choice.label}</option>)}</select></label><label>Reveal<select value={draft.reveal_mode} disabled={locked} onChange={(event) => setDraft({ ...draft, reveal_mode: event.target.value })}><option value="manual">Manual</option><option value="auto">When all voted</option></select></label>{locked && <p className="settings-note">Scale and reveal mode lock after tickets are added.</p>}{error && <p className="form-error">{error}</p>}<div className="modal-actions"><button className="secondary" onClick={onClose}>Cancel</button><button className="primary" onClick={onSave}>Save settings</button></div></section></div>
}

function Results({ selected, onEstimate, onNext, onRevote }) {
  const [finalEstimate, setFinalEstimate] = useState(!Number.isNaN(Number(selected)) ? selected : '5')
  const votes = [selected, '5', '8', '5']
  return <section className="results"><div className="result-cards">{team.map((person, index) => <div key={person.initials}><strong>{votes[index]}</strong><span>{person.name}</span></div>)}</div><div className="consensus"><div><strong>5.8</strong><span>Average</span></div><div><strong>5–8</strong><span>Range</span></div><div><strong className="good">Close</strong><span>Consensus</span></div></div><div className="final-estimate"><p className="micro-label">Set final estimate</p><div>{['0', '1', '2', '3', '5', '8', '13', '21'].map((point) => <button className={finalEstimate === point ? 'active' : ''} key={point} onClick={() => setFinalEstimate(point)}>{point}</button>)}</div></div><div className="result-actions"><button className="secondary" onClick={onRevote}>Re-vote</button><button className="primary" onClick={() => { onEstimate(finalEstimate); onNext() }}>Save & next <span>→</span></button></div></section>
}

function CenteredState({ eyebrow, title, detail, action }) {
  return <main className="centered-state"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{detail && <p>{detail}</p>}{action}</main>
}

function Toast({ children }) { return <div className="toast" role="status">{children}</div> }
function Back({ children, onClick }) { return <button className="back" onClick={onClick}>← {children}</button> }

function Shell({ children, status, user, onRooms }) {
  const logOut = async () => { await signOut(); pushPath('/') }
  return <div><header className="app-header"><button className="logo-button" onClick={onRooms}><Logo /></button><nav><button onClick={onRooms}>Rooms</button><button disabled>People</button>{!user.isDevelopment && <button onClick={logOut}>Sign out</button>}<button className="avatar" aria-label={user.displayName}>{initials(user.displayName)}</button></nav></header>{children}<footer className="app-footer"><Logo /><span><i className={status ? 'online' : ''} /> {status ? 'API connected' : 'API unavailable'}</span></footer></div>
}

export default App
