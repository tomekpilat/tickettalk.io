import { useState } from 'react'
import { ticketDistribution } from '../lib/workspace.js'

const chartColors = ['#0f9d76', '#1d4f47', '#d3a95f', '#d96c4f', '#68798a', '#a4778b']

function chartGradient(distribution) {
  let cursor = 0
  return distribution.map((item, index) => {
    const start = cursor
    cursor += item.share * 100
    return `${chartColors[index % chartColors.length]} ${start}% ${cursor}%`
  }).join(', ')
}

export function TicketDistributionChart({ tickets }) {
  const distribution = ticketDistribution(tickets)
  const assigned = tickets.length - (distribution.find((item) => item.assignee === 'Unassigned')?.count || 0)
  const gradient = distribution.length ? chartGradient(distribution) : 'var(--line) 0% 100%'
  return (
    <section className="panel distribution-panel" aria-label="Ticket distribution by assignee">
      <div className="panel-label"><span>Ticket distribution</span><small>Final ownership</small></div>
      <div className="distribution-content">
        <div className="distribution-donut" style={{ background: `conic-gradient(${gradient})` }} role="img" aria-label={`${assigned} of ${tickets.length} tickets assigned`}>
          <span><strong>{tickets.length}</strong><small>tickets</small></span>
        </div>
        <div className="distribution-legend">{distribution.map((item, index) => (
          <div key={item.assignee}>
            <i style={{ background: chartColors[index % chartColors.length] }} />
            <span><strong>{item.assignee}</strong><small>{item.count} {item.count === 1 ? 'ticket' : 'tickets'} · {item.points} pts</small></span>
            <b>{Math.round(item.share * 100)}%</b>
          </div>
        ))}</div>
      </div>
    </section>
  )
}

function AssigneePicker({ ticket, loadUsers, onSelect, disabled }) {
  const [options, setOptions] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const open = async () => {
    setLoading(true)
    setError('')
    try {
      setOptions(await loadUsers(''))
    } catch (nextError) {
      setError(nextError.message)
    } finally {
      setLoading(false)
    }
  }

  if (!options) return <div className="assignee-picker"><span>{ticket.final_assignee_display_name || 'Unassigned'}</span>{!disabled && <button className="secondary" disabled={loading} onClick={open}>{loading ? 'Loading…' : 'Reassign'}</button>}{error && <small>{error}</small>}</div>
  return <div className="assignee-picker"><select aria-label={`Final assignee for ${ticket.issue_key}`} value={ticket.final_assignee_account_id || ''} onChange={(event) => { const option = options.find((item) => item.account_id === event.target.value); onSelect(option || null) }}><option value="">Unassigned</option>{options.map((option) => <option value={option.account_id} key={option.account_id}>{option.display_name}</option>)}</select><button className="secondary" onClick={() => setOptions(null)}>Done</button></div>
}

function SummaryTicketRow({ ticket, scale, isFacilitator, loadAssignees, onAssignee, onEstimate }) {
  const [savingEstimate, setSavingEstimate] = useState(false)
  const saveEstimate = async (value) => {
    setSavingEstimate(true)
    try {
      await onEstimate(ticket, value)
    } finally {
      setSavingEstimate(false)
    }
  }
  const label = ticket.issue_key || ticket.summary
  return (
    <div className="summary-ticket-row">
      <span>{ticket.issue_key || 'Manual'}</span>
      <strong>{ticket.summary}</strong>
      {ticket.jira_issue_id
        ? <AssigneePicker ticket={ticket} disabled={!isFacilitator} loadUsers={(query) => loadAssignees(ticket, query)} onSelect={(option) => onAssignee(ticket, option)} />
        : <span className="manual-owner">Not linked to Jira</span>}
      {isFacilitator
        ? <select aria-label={`Final estimate for ${label}`} disabled={savingEstimate} value={ticket.final_estimate || ''} onChange={(event) => saveEstimate(event.target.value)}><option value="" disabled>—</option>{scale.filter((value) => value !== '?').map((value) => <option value={value} key={value}>{value}</option>)}</select>
        : <b>{ticket.final_estimate ?? '—'}</b>}
    </div>
  )
}

export function SummaryPlanningPanel({
  tickets,
  scale,
  isFacilitator,
  loadAssignees,
  onAssignee,
  onEstimate,
}) {
  return (
    <section className="summary-planning">
      <TicketDistributionChart tickets={tickets} />
      <div className="panel summary-ticket-table">
        <div className="summary-ticket-row summary-ticket-head"><span>Key</span><strong>Ticket</strong><span>Final assignee</span><span>Price</span></div>
        {tickets.map((ticket) => <SummaryTicketRow key={ticket.id} ticket={ticket} scale={scale} isFacilitator={isFacilitator} loadAssignees={loadAssignees} onAssignee={onAssignee} onEstimate={onEstimate} />)}
      </div>
    </section>
  )
}
