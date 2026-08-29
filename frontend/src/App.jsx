import { useCallback, useEffect, useState } from 'react'
import { JiraConnectForm, JiraImportPanel, JiraWritebackPanel } from './components/JiraPanels.jsx'
import { SummaryPlanningPanel } from './components/SummaryPlanning.jsx'
import { setAnonymousDisplayName, useAuth } from './lib/auth.js'
import { api } from './lib/api.js'
import { isRoomLikePath, pushPath, roomIdFromPath, roomPath } from './lib/routing.js'
import { subscribeToRoom } from './lib/supabase.js'
import { completionPercentage, remainingTicketIndex, roomView } from './lib/workspace.js'

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

const sampleImport = 'Issue key,Summary,Issue Type\nPAY-201,Add wallet balance alert,Story\nPAY-205,Fix duplicate webhook delivery,Bug'
const emptyTicketDraft = { issue_key: '', summary: '', issue_type: 'Story', description: '' }
const jiraIssueKeyPattern = /^[A-Z][A-Z0-9_]*-\d+$/

function Logo() {
  return <div className="logo"><span>ticket<strong>talk.</strong></span></div>
}

function initials(name) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || 'TT'
}

function TicketDescription({ description }) {
  const paragraphs = (description?.trim() || 'No ticket description supplied.')
    .split(/\r?\n+/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)

  return <div className="description">{paragraphs.map((paragraph, index) => <p key={`${index}-${paragraph}`}>{paragraph}</p>)}</div>
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
      onJoining={() => setJoiningRoomId(sharedRoomId)}
      onJoined={() => setJoiningRoomId(null)}
    />
  )
  if (!auth.user && isRoomLikePath()) return <CenteredState eyebrow="Room access" title="Room link not recognized." detail="Check the URL and ask the facilitator for a new link." />
  if (!auth.user) return <CenteredState eyebrow="Session" title="A private browser session could not be created." detail="Refresh the page to try again." />
  return <Workspace user={auth.user} />
}

function Workspace({ user }) {
  const [view, setView] = useState('rooms')
  const [rooms, setRooms] = useState([])
  const [room, setRoom] = useState(null)
  const [members, setMembers] = useState([])
  const [tickets, setTickets] = useState([])
  const [ticketIndex, setTicketIndex] = useState(0)
  const [voteSubmitted, setVoteSubmitted] = useState(false)
  const [choosingVote, setChoosingVote] = useState(false)
  const [submittingVote, setSubmittingVote] = useState(false)
  const [voteResults, setVoteResults] = useState(null)
  const [showDetail, setShowDetail] = useState(false)
  const [roomName, setRoomName] = useState('Sprint 43 planning')
  const [facilitatorName, setFacilitatorName] = useState(
    user.displayName === 'Guest' || user.displayName === 'Facilitator' ? '' : user.displayName,
  )
  const [roomScale, setRoomScale] = useState('fibonacci')
  const [revealMode, setRevealMode] = useState('manual')
  const [importText, setImportText] = useState(sampleImport)
  const [importMode, setImportMode] = useState('csv')
  const [duplicateBehavior, setDuplicateBehavior] = useState('error')
  const [importPreview, setImportPreview] = useState(null)
  const [jiraConnection, setJiraConnection] = useState(null)
  const [jiraDraft, setJiraDraft] = useState({ site_url: '', email: '', api_token: '' })
  const [jiraIssueKey, setJiraIssueKey] = useState('')
  const [jql, setJql] = useState('project = PAY AND resolution = Unresolved ORDER BY Rank ASC')
  const [jiraPreview, setJiraPreview] = useState(null)
  const [jiraConnecting, setJiraConnecting] = useState(false)
  const [jiraAddingIssue, setJiraAddingIssue] = useState(false)
  const [jiraSearching, setJiraSearching] = useState(false)
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
  const [writingJira, setWritingJira] = useState(false)
  const [jiraWriteback, setJiraWriteback] = useState(null)

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
      if (nextRoom.owner_id === user.id) {
        try {
          setJiraConnection(await api.jiraConnection(roomId))
        } catch (error) {
          if (error.status !== 404) setToast(error.message)
          setJiraConnection(null)
        }
      } else {
        setJiraConnection(null)
      }
      setVoteSubmitted(nextMembers.some((member) => member.user_id === user.id && member.has_voted))
      setChoosingVote(false)
      const activeIndex = Math.max(0, nextTickets.findIndex((ticket) => ticket.id === nextRoom.active_ticket_id))
      setTicketIndex(activeIndex)
      if (nextTickets[activeIndex]?.vote_state === 'revealed') {
        setVoteResults(await api.voteResults(roomId, nextTickets[activeIndex].id))
      } else {
        setVoteResults(null)
      }
      setView(roomView(nextRoom, nextTickets))
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
  }, [user.id])

  const goToRooms = useCallback(() => {
    pushPath('/')
    setView('rooms')
    setRoom(null)
    setTickets([])
    setMembers([])
    setRouteError(null)
    setSettingsOpen(false)
    setJiraConnection(null)
    setJiraIssueKey('')
    setJiraPreview(null)
    setJiraWriteback(null)
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
        if (freshRoom.active_ticket_id) {
          const activeIndex = freshTickets.findIndex(
            (ticket) => ticket.id === freshRoom.active_ticket_id
          )
          if (activeIndex >= 0) {
            setVoteSubmitted(freshMembers.some(
              (member) => member.user_id === user.id && member.has_voted
            ))
            const activeTicketChanged = freshRoom.active_ticket_id !== room.active_ticket_id
            if (activeTicketChanged) setChoosingVote(false)
            setTicketIndex(activeIndex)
            if (freshTickets[activeIndex].vote_state === 'revealed') {
              setVoteResults(await api.voteResults(room.id, freshTickets[activeIndex].id))
            } else {
              setVoteResults(null)
            }
            if (activeTicketChanged) setView('session')
          }
        } else if (room.active_ticket_id) {
          setVoteSubmitted(false)
          setChoosingVote(false)
          setVoteResults(null)
          setView(roomView(freshRoom, freshTickets))
        }
      } catch { /* the next user action will surface connectivity or authorization */ }
    })
  }, [room?.active_ticket_id, room?.id, user.id])

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
  const completion = completionPercentage(tickets)
  const nextUnsizedIndex = tickets.findIndex((item) => item.final_estimate == null)
  const remainingUnsizedIndex = remainingTicketIndex(tickets, ticketIndex)
  const votingScale = scales[room?.scale] || scales.fibonacci
  const isFacilitator = Boolean(room && room.owner_id === user.id)

  useEffect(() => {
    if (!room?.id || view !== 'import' || importMode !== 'csv' || !isFacilitator || !importText.trim()) {
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
  }, [duplicateBehavior, importMode, importText, isFacilitator, room?.id, view])

  const createRoom = async () => {
    setFormError('')
    const normalizedFacilitatorName = facilitatorName.trim().replace(/\s+/g, ' ')
    if (!normalizedFacilitatorName) {
      setFormError('Enter your name to create a room.')
      return
    }
    if (roomName.trim().length < 3) {
      setFormError('Room name needs at least 3 characters.')
      return
    }
    setCreating(true)
    try {
      await setAnonymousDisplayName(normalizedFacilitatorName)
      const created = await api.createRoom({
        name: roomName,
        scale: roomScale,
        reveal_mode: revealMode,
        display_name: normalizedFacilitatorName,
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

  const openCreateRoom = () => {
    setFormError('')
    setView('create-room')
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

  const connectJira = async (event) => {
    event.preventDefault()
    setFormError('')
    setJiraConnecting(true)
    try {
      const connected = await api.connectJira(room.id, jiraDraft)
      setJiraConnection(connected)
      setJiraDraft((draft) => ({ ...draft, api_token: '' }))
      setToast(`Connected as ${connected.jira_display_name}`)
    } catch (error) {
      setFormError(error.message)
    } finally {
      setJiraConnecting(false)
    }
  }

  const searchJira = async () => {
    if (!jql.trim()) return
    setFormError('')
    setJiraSearching(true)
    try {
      setJiraPreview(await api.searchJira(room.id, jql, duplicateBehavior))
    } catch (error) {
      setJiraPreview(null)
      setFormError(error.message)
    } finally {
      setJiraSearching(false)
    }
  }

  const addJiraIssue = async (event) => {
    event.preventDefault()
    const issueKey = jiraIssueKey.trim().toUpperCase()
    if (!jiraIssueKeyPattern.test(issueKey)) {
      setFormError('Enter a complete Jira issue key, for example PAY-123.')
      return
    }

    const exactJql = `key = "${issueKey}"`
    setFormError('')
    setJiraAddingIssue(true)
    try {
      const preview = await api.searchJira(room.id, exactJql, duplicateBehavior)
      if (preview.errors.length) {
        setFormError(preview.errors.map((error) => error.message).join(' '))
        return
      }
      if (preview.source_count !== 1) {
        setFormError(`${issueKey} was not found or is not visible to the connected Jira account.`)
        return
      }
      if (preview.saved_count !== 1) {
        setToast(`${issueKey} is already in this room`)
        return
      }

      const result = await api.importJira(room.id, exactJql, duplicateBehavior)
      setTickets(result.tickets)
      setRoom((currentRoom) => ({ ...currentRoom, ticket_count: result.tickets.length }))
      setJiraIssueKey('')
      setToast(`${issueKey} added to the backlog`)
      setView('backlog')
    } catch (error) {
      setFormError(error.message)
    } finally {
      setJiraAddingIssue(false)
    }
  }

  const selectJiraField = async (fieldId) => {
    try {
      setJiraConnection(await api.selectJiraStoryPointsField(room.id, fieldId))
      setToast('Jira estimate field updated')
    } catch (error) {
      setToast(error.message)
    }
  }

  const disconnectJira = async () => {
    if (!window.confirm('Disconnect Jira and remove this room’s stored credential?')) return
    try {
      await api.disconnectJira(room.id)
      setJiraConnection(null)
      setJiraPreview(null)
      setToast('Jira disconnected')
    } catch (error) {
      setToast(error.message)
    }
  }

  const saveJiraImport = async () => {
    if (!jiraPreview?.saved_count || jiraPreview.errors.length) return
    setImporting(true)
    setFormError('')
    try {
      const result = await api.importJira(room.id, jql, duplicateBehavior)
      setTickets(result.tickets)
      setRoom((currentRoom) => ({ ...currentRoom, ticket_count: result.tickets.length }))
      setToast(`${result.imported_count + result.replaced_count} Jira tickets saved`)
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
      const freshRoom = await api.room(room.id)
      const remaining = tickets.filter((item) => item.id !== ticket.id)
        .map((item, position) => ({ ...item, position }))
      setTickets(remaining)
      setRoom(freshRoom)
      setToast('Ticket removed')
      if (ticket.id === room.active_ticket_id) {
        setVoteSubmitted(false)
        setChoosingVote(false)
        setVoteResults(null)
        const replacementIndex = remaining.findIndex(
          (item) => item.id === freshRoom.active_ticket_id
        )
        if (replacementIndex >= 0) {
          setTicketIndex(replacementIndex)
          setView('session')
        } else {
          setView(remaining.length ? 'backlog' : 'import')
        }
      } else if (!remaining.length) {
        setView('import')
      }
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

  const openTicket = async (index, options = {}) => {
    if (!isFacilitator || index < 0 || index >= tickets.length) return
    const target = tickets[index]
    if (!options.skipEstimateWarning && view === 'session' && target.id !== current?.id && current?.vote_state === 'revealed' && !current.final_estimate) {
      const proceed = window.confirm('This ticket has no final estimate. Move on anyway?')
      if (!proceed) return
    }
    try {
      const updatedRoom = await api.setActiveTicket(room.id, target.id)
      const freshMembers = await refreshMembers(room.id)
      setRoom(updatedRoom)
      setTicketIndex(index)
      setVoteSubmitted(freshMembers.some(
        (member) => member.user_id === user.id && member.has_voted
      ))
      setChoosingVote(false)
      setVoteResults(target.vote_state === 'revealed' ? await api.voteResults(room.id, target.id) : null)
      setView('session')
    } catch (error) {
      setToast(error.message)
    }
  }

  const submitVote = async (value) => {
    if (!current || submittingVote) return
    setSubmittingVote(true)
    try {
      const receipt = await api.submitVote(room.id, current.id, value)
      setVoteSubmitted(true)
      setChoosingVote(false)
      await refreshMembers(room.id)
      if (receipt.revealed) {
        const [freshTickets, results] = await Promise.all([
          api.tickets(room.id), api.voteResults(room.id, current.id),
        ])
        setTickets(freshTickets)
        setVoteResults(results)
      }
    } catch (error) {
      setToast(error.message)
    } finally {
      setSubmittingVote(false)
    }
  }

  const revealVotes = async () => {
    try {
      const results = await api.revealVotes(room.id, current.id)
      setVoteResults(results)
      setTickets((items) => items.map((item) => (
        item.id === current.id ? { ...item, vote_state: 'revealed' } : item
      )))
    } catch (error) {
      setToast(error.message)
    }
  }

  const restartVote = async () => {
    try {
      const results = await api.restartVote(room.id, current.id)
      setVoteResults(null)
      setVoteSubmitted(false)
      setChoosingVote(false)
      setMembers((items) => items.map((member) => ({ ...member, has_voted: false })))
      setTickets((items) => items.map((item) => (
        item.id === current.id
          ? { ...item, vote_state: 'voting', vote_round: results.round, final_estimate: null }
          : item
      )))
    } catch (error) {
      setToast(error.message)
    }
  }

  const saveFinalEstimate = async (value) => {
    try {
      const updated = await api.setFinalEstimate(room.id, current.id, value)
      setTickets((items) => items.map((item) => item.id === updated.id ? updated : item))
      setVoteResults((results) => ({ ...results, final_estimate: updated.final_estimate }))
      setToast('Final estimate saved')
      return true
    } catch (error) {
      setToast(error.message)
      return false
    }
  }

  const exportCsv = () => {
    api.downloadRoomExport(room.id).then(({ blob, filename }) => {
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = filename
      link.click()
      URL.revokeObjectURL(link.href)
    }).catch((error) => setToast(error.message))
  }

  const saveJiraAssignee = async (ticket, userOption) => {
    try {
      const updated = await api.setJiraAssignee(
        room.id, ticket.id, userOption?.account_id || null, userOption?.display_name || null,
      )
      setTickets((items) => items.map((item) => item.id === updated.id ? updated : item))
      setToast('Final Jira assignee saved')
    } catch (error) {
      setToast(error.message)
    }
  }

  const saveSummaryEstimate = async (ticket, value) => {
    try {
      const updated = await api.setFinalEstimate(room.id, ticket.id, value)
      setTickets((items) => items.map((item) => item.id === updated.id ? updated : item))
      setToast(`${ticket.issue_key || 'Ticket'} price updated`)
      return true
    } catch (error) {
      setToast(error.message)
      return false
    }
  }

  const writeResultsToJira = async () => {
    if (!window.confirm('Write final estimates and assignees to Jira?')) return
    setWritingJira(true)
    setJiraWriteback(null)
    try {
      const result = await api.writebackJira(room.id)
      setJiraWriteback(result)
      setTickets(await api.tickets(room.id))
      setToast(result.failed_count ? `${result.failed_count} Jira updates failed` : 'Jira updated')
    } catch (error) {
      setToast(error.message)
    } finally {
      setWritingJira(false)
    }
  }

  const deleteRoom = async () => {
    const confirmation = window.prompt(`Type the room name to delete it permanently:\n\n${room.name}`)
    if (confirmation !== room.name) {
      if (confirmation !== null) setFormError(`Type “${room.name}” exactly to confirm deletion.`)
      return
    }
    try {
      await api.deleteRoom(room.id)
      goToRooms()
    } catch (error) {
      setFormError(error.message)
    }
  }

  const nextTicket = (options = {}) => openTicket(ticketIndex + 1, options)

  const finishVoting = async () => {
    try {
      const updatedRoom = await api.setActiveTicket(room.id, null)
      setRoom(updatedRoom)
      setVoteSubmitted(false)
      setChoosingVote(false)
      setVoteResults(null)
      setView('summary')
      setToast('Voting complete')
    } catch (error) {
      setToast(error.message)
    }
  }

  const continueAfterEstimate = (options = {}) => (
    remainingUnsizedIndex < 0
      ? finishVoting()
      : openTicket(remainingUnsizedIndex, options)
  )
  const votedCount = members.filter((member) => member.has_voted).length

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
      defaultName={user.displayName}
      onJoined={() => openRoom(roomIdFromPath(), { push: false })}
    />
  )

  if (view === 'route-error') return (
    <Shell status={apiOnline} user={user} onRooms={goToRooms}>
      <CenteredState eyebrow="Room access" title={routeError?.title || 'Room unavailable.'} detail={routeError?.detail} action={<button className="primary" onClick={goToRooms}>Back to rooms</button>} />
    </Shell>
  )

  if (view === 'create-room') return (
    <Shell status={apiOnline} user={user} onRooms={goToRooms}>
      <main className="page create-room-page">
        <div className="page-toolbar"><Back onClick={goToRooms}>Home</Back></div>
        <section className="page-heading">
          <div><p className="eyebrow">New conversation</p><h1>Create a pricing room</h1><p>Choose how the team will estimate, then share the private room link.</p></div>
          <div className="account-caption"><span>{user.displayName}</span><small>Facilitator</small></div>
        </section>
        <div className="new-room panel">
          <div className="panel-label"><span>Room setup</span><small>01</small></div>
          <p className="settings-note">No registration. The unique room link is the private access key for your team.</p>
          <label>Your name<input value={facilitatorName} onChange={(event) => setFacilitatorName(event.target.value)} maxLength={80} placeholder="e.g. Maya" /></label>
          <label>Room name<input value={roomName} onChange={(event) => setRoomName(event.target.value)} maxLength={120} /></label>
          <fieldset className="choice-field"><legend>Scale</legend>{scaleChoices.map((choice) => <button key={choice.value} className={roomScale === choice.value ? 'choice active' : 'choice'} onClick={() => setRoomScale(choice.value)}><strong>{choice.label}</strong><small>{choice.hint}</small></button>)}</fieldset>
          <fieldset className="choice-field"><legend>Reveal</legend><div className="segmented"><button className={revealMode === 'manual' ? 'active' : ''} onClick={() => setRevealMode('manual')}>Manual</button><button className={revealMode === 'auto' ? 'active' : ''} onClick={() => setRevealMode('auto')}>When all voted</button></div></fieldset>
          {formError && <p className="form-error">{formError}</p>}
          <button className="primary wide" disabled={creating} onClick={createRoom}>{creating ? 'Creating room…' : 'Create pricing room'} <span>→</span></button>
        </div>
      </main>
    </Shell>
  )

  if (view === 'rooms') return (
    <Shell status={apiOnline} user={user} onRooms={goToRooms}>
      <main className="page home-page">
        <section className="home-hero">
          <div className="home-copy">
            <p className="eyebrow">Planning poker / without ceremony</p>
            <h1>Talk through the work.<br />Leave with a price.</h1>
            <p>tickettalk gives product teams one focused place to discuss stories, vote privately, and capture the estimate everyone can stand behind.</p>
            <div className="home-actions"><button className="primary" onClick={openCreateRoom}>Start a room <span>→</span></button><span>No registration required</span></div>
          </div>
          <aside className="home-principles panel" aria-label="How tickettalk works">
            <div className="panel-label"><span>One useful conversation</span><small>03 steps</small></div>
            <div className="home-principle"><small>01</small><span><strong>Bring the stories</strong><em>Import Jira work or add tickets manually.</em></span></div>
            <div className="home-principle"><small>02</small><span><strong>Vote without influence</strong><em>Estimates stay hidden until reveal.</em></span></div>
            <div className="home-principle"><small>03</small><span><strong>Leave with decisions</strong><em>Save final prices and export the summary.</em></span></div>
          </aside>
        </section>
        <section className="home-rooms">
          <div className="home-rooms-heading"><div><p className="eyebrow">Your workspace</p><h2>Recent rooms</h2></div><button className="secondary" onClick={openCreateRoom}>New room <span>+</span></button></div>
          {!rooms.length && <div className="empty-state">No rooms yet. Start a room when your team is ready to price the next piece of work.</div>}
          <div className="home-room-grid">{rooms.map((item) => <button className="room-card" key={item.id} onClick={() => openRoom(item.id)}>
            <div className="room-card-top"><div><small>{item.scale}</small><h2>{item.name}</h2></div><span className="arrow">↗</span></div>
            <div className="progress"><i style={{ width: `${item.ticket_count ? (item.sized_count / item.ticket_count) * 100 : 0}%` }} /></div>
            <div className="room-meta"><span>{item.sized_count} / {item.ticket_count} sized</span><span>{item.total_points} pts</span></div>
          </button>)}</div>
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
        <div className="split-heading"><div><p className="eyebrow">{room.name} / import</p><h1>Bring in the tickets.</h1></div><p>Add one Jira issue by key, pull a set with JQL, or paste a CSV export. The source context stays attached to every estimate.</p></div>
        <ParticipantRoster members={members} currentUserId={user.id} compact />
        <div className="import-tabs segmented" aria-label="Import source"><button className={importMode === 'jira' ? 'active' : ''} onClick={() => setImportMode('jira')}>Jira + JQL</button><button className={importMode === 'csv' ? 'active' : ''} onClick={() => setImportMode('csv')}>CSV / TSV</button></div>
        {formError && <p className="form-error inline-error">{formError}</p>}
        {importMode === 'csv' && <section className="import-grid">
          <div className="panel import-editor"><div className="panel-label"><span>CSV or TSV input</span><small>01</small></div><textarea aria-label="Jira import" value={importText} onChange={(event) => setImportText(event.target.value)} /><label className="duplicate-choice">Existing Jira keys<select value={duplicateBehavior} onChange={(event) => setDuplicateBehavior(event.target.value)}><option value="error">Ask me to decide</option><option value="skip">Skip existing</option><option value="replace">Replace existing</option></select></label><div className="editor-actions"><label className="secondary file-picker">Choose file<input type="file" accept=".csv,.tsv,.txt" onChange={(event) => loadImportFile(event.target.files?.[0])} /></label><span>Maximum 1 MB · 500 tickets</span></div></div>
          <div className="panel preview"><div className="panel-label"><span>Validated preview</span><small>{String(importPreview?.source_count || 0).padStart(2, '0')}</small></div>{previewing && <p className="preview-message">Checking rows…</p>}{importPreview?.errors.map((error) => <div className="import-error" key={`${error.row_number}-${error.field}`}><strong>Row {error.row_number || '—'} · {error.field}</strong><span>{error.message}</span><small>{error.fix}</small></div>)}{!previewing && importPreview?.rows.map((item) => <div className="preview-row" key={`${item.row_number}-${item.issue_key || item.summary}`}><span>{item.issue_key || 'Manual'}</span><p>{item.summary}</p><small>{item.action}</small></div>)}<div className="preview-counts"><span>{importPreview?.saved_count || 0} to save</span><span>{importPreview?.skipped_count || 0} skipped</span></div><button className="primary wide" disabled={previewing || importing || !importPreview?.saved_count || importPreview.errors.length > 0} onClick={saveImport}>{importing ? 'Saving tickets…' : `Save ${importPreview?.saved_count || 0} to backlog`} <span>→</span></button></div>
        </section>}
        {importMode === 'jira' && !jiraConnection && <JiraConnectForm draft={jiraDraft} setDraft={setJiraDraft} connecting={jiraConnecting} onConnect={connectJira} />}
        {importMode === 'jira' && jiraConnection && <JiraImportPanel connection={jiraConnection} issueKey={jiraIssueKey} setIssueKey={setJiraIssueKey} addingIssue={jiraAddingIssue} jql={jql} setJql={setJql} duplicateBehavior={duplicateBehavior} setDuplicateBehavior={setDuplicateBehavior} preview={jiraPreview} searching={jiraSearching} importing={importing} onSelectField={selectJiraField} onDisconnect={disconnectJira} onAddIssue={addJiraIssue} onSearch={searchJira} onImport={saveJiraImport} />}
        <div className="manual-entry"><span>Not in Jira?</span><button className="secondary" onClick={openNewTicket}>Add a ticket manually</button></div>
      </main>
      {settingsOpen && <RoomSettings room={room} draft={settingsDraft} setDraft={setSettingsDraft} ticketCount={tickets.length} error={formError} onClose={() => setSettingsOpen(false)} onSave={saveSettings} onDelete={deleteRoom} />}
      {ticketDraft && <TicketEditor draft={ticketDraft} setDraft={setTicketDraft} editing={Boolean(editingTicketId)} error={formError} onClose={() => setTicketDraft(null)} onSave={saveTicketDraft} />}
      {toast && <Toast>{toast}</Toast>}
    </Shell>
  )

  if (view === 'backlog') return (
    <Shell status={apiOnline} user={user} onRooms={goToRooms}>
      <main className="page backlog-page">
        <div className="page-toolbar"><Back onClick={goToRooms}>Rooms</Back>{roomActions}</div>
        <section className="page-heading"><div><p className="eyebrow">{room.name}</p><h1>Backlog</h1><p>{completion}% priced · {tickets.filter((ticket) => ticket.final_estimate == null).length} tickets need a conversation</p></div>{isFacilitator && <div className="heading-actions"><button className="secondary" onClick={openNewTicket}>Add ticket</button><button className="primary" disabled={nextUnsizedIndex < 0} onClick={() => openTicket(nextUnsizedIndex)}>Price next ticket <span>→</span></button></div>}</section>
        <ParticipantRoster members={members} currentUserId={user.id} compact />
        <BacklogTable tickets={tickets} isFacilitator={isFacilitator} onOpen={openTicket} onEdit={openTicketEditor} onDelete={deleteBacklogTicket} onMove={moveBacklogTicket} />
      </main>
      {settingsOpen && <RoomSettings room={room} draft={settingsDraft} setDraft={setSettingsDraft} ticketCount={tickets.length} error={formError} onClose={() => setSettingsOpen(false)} onSave={saveSettings} onDelete={deleteRoom} />}
      {ticketDraft && <TicketEditor draft={ticketDraft} setDraft={setTicketDraft} editing={Boolean(editingTicketId)} error={formError} onClose={() => setTicketDraft(null)} onSave={saveTicketDraft} />}
      {toast && <Toast>{toast}</Toast>}
    </Shell>
  )

  if (view === 'summary') return (
    <Shell status={apiOnline} user={user} onRooms={goToRooms}>
      <main className="page summary-page">
        <div className="page-toolbar"><Back onClick={() => setView(room.active_ticket_id ? 'session' : 'backlog')}>{room.active_ticket_id ? 'Session' : 'Backlog'}</Back>{roomActions}</div>
        <section className="page-heading"><div><p className="eyebrow">{room.name}</p><h1>Pricing summary</h1></div>{isFacilitator && <button className="secondary" onClick={exportCsv}>Export CSV ↓</button>}</section>
        <ParticipantRoster members={members} currentUserId={user.id} compact />
        <div className="summary-stats"><div><strong>{tickets.reduce((sum, item) => sum + (Number(item.final_estimate) || 0), 0)}</strong><span>Total points</span></div><div><strong>{tickets.filter((item) => item.final_estimate != null).length}</strong><span>Tickets sized</span></div><div><strong>{completion}%</strong><span>Complete</span></div></div>
        <SummaryPlanningPanel tickets={tickets} scale={votingScale} isFacilitator={isFacilitator} loadAssignees={(ticket, query) => api.jiraAssignees(room.id, ticket.id, query)} onAssignee={saveJiraAssignee} onEstimate={saveSummaryEstimate} />
        {isFacilitator && tickets.some((ticket) => ticket.jira_issue_id) && <JiraWritebackPanel connection={jiraConnection} tickets={tickets} scale={room.scale} result={jiraWriteback} writing={writingJira} onWriteback={writeResultsToJira} />}
      </main>
      {settingsOpen && <RoomSettings room={room} draft={settingsDraft} setDraft={setSettingsDraft} ticketCount={tickets.length} error={formError} onClose={() => setSettingsOpen(false)} onSave={saveSettings} onDelete={deleteRoom} />}
      {toast && <Toast>{toast}</Toast>}
    </Shell>
  )

  return (
    <div className="session-shell">
      <header className="session-top">{isFacilitator ? <Back onClick={() => setView('backlog')}>Backlog</Back> : <span className="session-role">Live session</span>}<div><strong>{room.name}</strong><span>{ticketIndex + 1} of {tickets.length}</span></div><div className="session-actions">{isFacilitator && <button onClick={shareRoom}>Share</button>}<button onClick={() => setShowDetail((value) => !value)}>{showDetail ? 'Hide' : 'Ticket'} detail</button><button onClick={() => setView('summary')}>Summary</button></div></header>
      <main className="session-main">
        <ParticipantRoster members={members} currentUserId={user.id} compact />
        <section className="story-copy"><p className="eyebrow">{current?.issue_key} · {current?.issue_type}</p><h1>{current?.summary}</h1>{showDetail && <TicketDescription description={current?.description} />}</section>
        {voteResults?.state === 'revealed' ? <Results results={voteResults} scale={votingScale} isFacilitator={isFacilitator} finishesVoting={remainingUnsizedIndex < 0} onEstimate={saveFinalEstimate} onNext={continueAfterEstimate} onRevote={restartVote} /> : <>{(!voteSubmitted || choosingVote) ? <section className="vote-area"><p className="micro-label">{voteSubmitted ? 'Choose a replacement estimate' : 'Choose your estimate'}</p><div className="cards">{votingScale.map((value) => <button key={value} disabled={submittingVote} onClick={() => submitVote(value)}>{value}</button>)}</div></section> : <section className="vote-safe-state" role="status"><strong>Vote submitted</strong><span>Your estimate stays hidden until the facilitator reveals the cards.</span><button className="secondary" onClick={() => setChoosingVote(true)}>Change vote</button></section>}<section className="waiting"><div className="avatars">{members.map((member) => <span className={member.has_voted ? 'voted' : ''} key={member.user_id}>{initials(member.display_name)}</span>)}</div><p>{votedCount} of {members.length} voted</p>{isFacilitator && <button className="reveal" disabled={votedCount === 0} onClick={revealVotes}>Reveal votes</button>}</section></>}
      </main>
      <footer className="ticket-rail"><button disabled={!isFacilitator || ticketIndex === 0} onClick={() => openTicket(ticketIndex - 1)} aria-label="Previous ticket">←</button><div>{tickets.map((item, index) => { const label = item.issue_key || `Manual ${index + 1}`; return <button key={item.id} disabled={!isFacilitator} className={index === ticketIndex ? 'active' : item.story_points != null ? 'done' : ''} onClick={() => openTicket(index)} aria-label={`Open ticket ${label}`} title={item.summary}>{label}</button> })}</div><button disabled={!isFacilitator || ticketIndex === tickets.length - 1} onClick={nextTicket} aria-label="Next ticket">→</button></footer>
      {toast && <Toast>{toast}</Toast>}
    </div>
  )
}

function JoinRoom({ roomId, defaultName = '', onJoining, onJoined }) {
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
      await setAnonymousDisplayName(normalizedName)
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
    const roleStatus = member.role === 'facilitator' ? `Facilitator${member.has_voted ? ' · voted' : ''}` : status
    return <div className="roster-person" key={member.user_id}><span className={member.is_online ? 'roster-avatar online' : 'roster-avatar'}>{initials(member.display_name)}</span><span><strong>{member.user_id === currentUserId ? `${member.display_name} (you)` : member.display_name}</strong><small>{roleStatus}</small></span><i className={member.has_voted ? 'member-status voted' : member.is_online ? 'member-status' : 'member-status offline'} aria-label={status} /></div>
  })}</div></section>
}

function BacklogTable({ tickets, isFacilitator, onOpen, onEdit, onDelete, onMove }) {
  return <div className="ticket-table panel"><div className="ticket-row ticket-head"><span>Key</span><span>Summary</span><span>Type</span><span>Estimate</span></div>{tickets.map((item, index) => <div className="backlog-row" key={item.id}><button className="ticket-row ticket-open" disabled={!isFacilitator} onClick={() => onOpen(index)}><span>{item.issue_key || 'Manual'}</span><strong>{item.summary}</strong><small>{item.issue_type}</small><b className={item.final_estimate == null ? 'empty-points' : ''}>{item.final_estimate ?? '—'}</b></button>{isFacilitator && <div className="ticket-actions"><button disabled={index === 0} onClick={() => onMove(index, -1)} aria-label={`Move ${item.summary} up`}>↑</button><button disabled={index === tickets.length - 1} onClick={() => onMove(index, 1)} aria-label={`Move ${item.summary} down`}>↓</button><button onClick={() => onEdit(item)} aria-label={`Edit ${item.summary}`}>Edit</button><button className="danger-text" onClick={() => onDelete(item)} aria-label={`Remove ${item.summary}`}>Remove</button></div>}</div>)}</div>
}

function TicketEditor({ draft, setDraft, editing, error, onClose, onSave }) {
  const submit = (event) => {
    event.preventDefault()
    onSave()
  }
  return <div className="modal-backdrop" role="presentation"><form className="settings-panel ticket-editor panel" role="dialog" aria-modal="true" aria-labelledby="ticket-editor-title" onSubmit={submit}><div className="panel-label"><span id="ticket-editor-title">{editing ? 'Edit ticket' : 'Add ticket'}</span><button type="button" onClick={onClose} aria-label="Close ticket editor">×</button></div><label>Issue key <small>Optional</small><input value={draft.issue_key} maxLength={40} onChange={(event) => setDraft({ ...draft, issue_key: event.target.value })} placeholder="PAY-123" /></label><label>Summary<input required value={draft.summary} maxLength={500} onChange={(event) => setDraft({ ...draft, summary: event.target.value })} /></label><label>Type<input required value={draft.issue_type} maxLength={80} onChange={(event) => setDraft({ ...draft, issue_type: event.target.value })} /></label><label>Description<textarea value={draft.description} maxLength={20000} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>{error && <p className="form-error">{error}</p>}<div className="modal-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button className="primary">{editing ? 'Save changes' : 'Add to backlog'}</button></div></form></div>
}

function RoomSettings({ draft, setDraft, ticketCount, error, onClose, onSave, onDelete }) {
  const locked = ticketCount > 0
  return <div className="modal-backdrop" role="presentation"><section className="settings-panel panel" role="dialog" aria-modal="true" aria-labelledby="room-settings-title"><div className="panel-label"><span id="room-settings-title">Room settings</span><button onClick={onClose} aria-label="Close settings">×</button></div><label>Room name<input value={draft.name} maxLength={120} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label><label>Scale<select value={draft.scale} disabled={locked} onChange={(event) => setDraft({ ...draft, scale: event.target.value })}>{scaleChoices.map((choice) => <option value={choice.value} key={choice.value}>{choice.label}</option>)}</select></label><label>Reveal<select value={draft.reveal_mode} disabled={locked} onChange={(event) => setDraft({ ...draft, reveal_mode: event.target.value })}><option value="manual">Manual</option><option value="auto">When all voted</option></select></label>{locked && <p className="settings-note">Scale and reveal mode lock after tickets are added.</p>}{error && <p className="form-error">{error}</p>}<div className="danger-zone"><span><strong>Delete this room</strong><small>Members, tickets, votes, and estimates will be removed.</small></span><button className="danger-text" onClick={onDelete}>Delete room</button></div><div className="modal-actions"><button className="secondary" onClick={onClose}>Cancel</button><button className="primary" onClick={onSave}>Save settings</button></div></section></div>
}

function Results({ results, scale, isFacilitator, finishesVoting, onEstimate, onNext, onRevote }) {
  const [finalEstimate, setFinalEstimate] = useState(results.final_estimate)
  useEffect(() => setFinalEstimate(results.final_estimate), [results.final_estimate])
  const range = results.minimum == null ? '—' : results.minimum === results.maximum
    ? String(results.minimum)
    : `${results.minimum}–${results.maximum}`
  const consensusLabels = {
    unanimous: 'Unanimous', close: 'Close', split: 'Discuss', not_numeric: 'Discuss',
  }
  const saveAndNext = async () => {
    if (!finalEstimate) return
    if (await onEstimate(finalEstimate)) onNext({ skipEstimateWarning: true })
  }
  return <section className="results"><div className="result-cards">{results.votes.map((vote) => <div key={vote.user_id}><strong>{vote.value}</strong><span>{vote.display_name}</span></div>)}</div><div className="consensus"><div><strong>{results.average ?? '—'}</strong><span>Average</span></div><div><strong>{range}</strong><span>Range</span></div><div><strong className={results.consensus === 'unanimous' || results.consensus === 'close' ? 'good' : ''}>{consensusLabels[results.consensus] || '—'}</strong><span>Consensus</span></div></div>{isFacilitator && <><div className="final-estimate"><p className="micro-label">Set final estimate</p><div>{scale.filter((point) => point !== '?').map((point) => <button className={finalEstimate === point ? 'active' : ''} key={point} onClick={() => setFinalEstimate(point)}>{point}</button>)}</div></div><div className="result-actions"><button className="secondary" onClick={onRevote}>Re-vote</button><button className="primary" disabled={!finalEstimate} onClick={saveAndNext}>{finishesVoting ? 'Save & finish' : 'Save & next'} <span>→</span></button></div></>}</section>
}

function CenteredState({ eyebrow, title, detail, action }) {
  return <main className="centered-state"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{detail && <p>{detail}</p>}{action}</main>
}

function Toast({ children }) { return <div className="toast" role="status">{children}</div> }
function Back({ children, onClick }) { return <button className="back" onClick={onClick}>← {children}</button> }

function Shell({ children, status, user, onRooms }) {
  return <div><header className="app-header"><button className="logo-button" aria-label="tickettalk" onClick={onRooms}><Logo /></button><nav><button onClick={onRooms}>Home</button><button className="avatar" aria-label={user.displayName}>{initials(user.displayName)}</button></nav></header>{children}<footer className="app-footer"><Logo /><span><i className={status ? 'online' : ''} /> {status ? 'API connected' : 'API unavailable'}</span></footer></div>
}

export default App
