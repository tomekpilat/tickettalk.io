import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SummaryPlanningPanel, TicketDistributionChart } from './SummaryPlanning.jsx'

const jiraTicket = {
  id: 'ticket-1',
  issue_key: 'PAY-1',
  summary: 'Add wallet alerts',
  jira_issue_id: '101',
  final_assignee_account_id: 'maya',
  final_assignee_display_name: 'Maya',
  final_estimate: '5',
}

describe('summary planning', () => {
  it('charts ticket ownership, points, and unassigned work', () => {
    render(<TicketDistributionChart tickets={[
      jiraTicket,
      { ...jiraTicket, id: 'ticket-2', issue_key: 'PAY-2', final_estimate: '3' },
      { ...jiraTicket, id: 'ticket-3', issue_key: 'PAY-3', final_assignee_account_id: null, final_assignee_display_name: null, final_estimate: '2' },
    ]} />)

    expect(screen.getByRole('img', { name: '2 of 3 tickets assigned' })).toBeVisible()
    expect(screen.getByText('Maya')).toBeVisible()
    expect(screen.getByText('2 tickets · 8 pts')).toBeVisible()
    expect(screen.getByText('Unassigned')).toBeVisible()
    expect(screen.getByText('1 ticket · 2 pts')).toBeVisible()
  })

  it('lets the facilitator reassign Jira work and edit its final estimate', async () => {
    const onAssignee = vi.fn()
    const onEstimate = vi.fn().mockResolvedValue(true)
    render(<SummaryPlanningPanel
      tickets={[jiraTicket]}
      scale={['1', '2', '3', '5', '8', '?']}
      isFacilitator
      loadAssignees={vi.fn().mockResolvedValue([
        { account_id: 'maya', display_name: 'Maya' },
        { account_id: 'alex', display_name: 'Alex' },
      ])}
      onAssignee={onAssignee}
      onEstimate={onEstimate}
    />)

    fireEvent.click(screen.getByRole('button', { name: 'Reassign' }))
    const assignee = await screen.findByLabelText('Final assignee for PAY-1')
    fireEvent.change(assignee, { target: { value: 'alex' } })
    expect(onAssignee).toHaveBeenCalledWith(jiraTicket, {
      account_id: 'alex', display_name: 'Alex',
    })

    fireEvent.change(screen.getByLabelText('Final estimate for PAY-1'), {
      target: { value: '8' },
    })
    await waitFor(() => expect(onEstimate).toHaveBeenCalledWith(jiraTicket, '8'))
  })

  it('keeps ownership and estimates read-only for participants', () => {
    render(<SummaryPlanningPanel
      tickets={[jiraTicket]}
      scale={['1', '2', '3', '5', '8', '?']}
      isFacilitator={false}
      loadAssignees={vi.fn()}
      onAssignee={vi.fn()}
      onEstimate={vi.fn()}
    />)

    expect(screen.queryByRole('button', { name: 'Reassign' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Final estimate for PAY-1')).not.toBeInTheDocument()
    expect(screen.getAllByText('5')).not.toHaveLength(0)
  })
})
