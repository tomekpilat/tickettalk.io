import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { JiraConnectForm, JiraImportPanel, JiraWritebackPanel } from './JiraPanels.jsx'

describe('Jira panels', () => {
  it('makes OAuth primary and keeps the API-token fallback controlled by the parent', () => {
    const setDraft = vi.fn()
    const onOAuthConnect = vi.fn((event) => event.preventDefault())
    const onApiTokenConnect = vi.fn((event) => event.preventDefault())
    render(<JiraConnectForm draft={{ site_url: '', email: '', api_token: '' }} setDraft={setDraft} connecting={false} onOAuthConnect={onOAuthConnect} onApiTokenConnect={onApiTokenConnect} />)

    fireEvent.change(screen.getByLabelText('Jira site URL'), {
      target: { value: 'https://example.atlassian.net' },
    })
    fireEvent.submit(screen.getByRole('button', { name: /Continue with Atlassian/ }).closest('form'))

    expect(setDraft).toHaveBeenCalledWith({
      site_url: 'https://example.atlassian.net', email: '', api_token: '',
    })
    expect(onOAuthConnect).toHaveBeenCalled()
    expect(screen.getByText('Advanced: connect with an API token')).toBeVisible()
    fireEvent.submit(screen.getByRole('button', { name: 'Connect with API token' }).closest('form'))
    expect(onApiTokenConnect).toHaveBeenCalled()
  })

  it('renders JQL errors and delegates connection actions', () => {
    const onSelectField = vi.fn()
    const onDisconnect = vi.fn()
    const onSearch = vi.fn()
    render(<JiraImportPanel
      connection={{
        oauth: true,
        site_url: 'https://example.atlassian.net',
        jira_display_name: 'Maya',
        story_points_field_id: 'customfield_1',
        story_points_fields: [{ id: 'customfield_1', name: 'Story Points' }, { id: 'customfield_2', name: 'Estimate' }],
      }}
      issueKey=""
      setIssueKey={vi.fn()}
      addingIssue={false}
      jql="project = PAY"
      setJql={vi.fn()}
      duplicateBehavior="error"
      setDuplicateBehavior={vi.fn()}
      preview={{ source_count: 1, saved_count: 0, skipped_count: 0, rows: [], errors: [{ row_number: 1, field: 'JQL', message: 'Invalid query', fix: 'Correct the query' }] }}
      searching={false}
      importing={false}
      onSelectField={onSelectField}
      onDisconnect={onDisconnect}
      onAddIssue={vi.fn((event) => event.preventDefault())}
      onSearch={onSearch}
      onImport={vi.fn()}
    />)

    fireEvent.change(screen.getByLabelText('Jira estimate field'), { target: { value: 'customfield_2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Disconnect' }))
    fireEvent.click(screen.getByRole('button', { name: 'Preview tickets' }))

    expect(screen.getByText('Invalid query')).toBeVisible()
    expect(screen.getByText('OAuth')).toBeVisible()
    expect(onSelectField).toHaveBeenCalledWith('customfield_2')
    expect(onDisconnect).toHaveBeenCalled()
    expect(onSearch).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /Import 0 tickets/ })).toBeDisabled()
  })

  it('delegates a single Jira issue key without requiring JQL', () => {
    const setIssueKey = vi.fn()
    const onAddIssue = vi.fn((event) => event.preventDefault())
    render(<JiraImportPanel
      connection={{
        site_url: 'https://example.atlassian.net',
        jira_display_name: 'Maya',
        story_points_fields: [],
      }}
      issueKey="PAY-123"
      setIssueKey={setIssueKey}
      addingIssue={false}
      jql="project = PAY"
      setJql={vi.fn()}
      duplicateBehavior="error"
      setDuplicateBehavior={vi.fn()}
      preview={null}
      searching={false}
      importing={false}
      onSelectField={vi.fn()}
      onDisconnect={vi.fn()}
      onAddIssue={onAddIssue}
      onSearch={vi.fn()}
      onImport={vi.fn()}
    />)

    fireEvent.change(screen.getByLabelText('Jira issue key'), {
      target: { value: 'PAY-456' },
    })
    fireEvent.submit(screen.getByRole('button', { name: /Add to room/ }).closest('form'))

    expect(setIssueKey).toHaveBeenCalledWith('PAY-456')
    expect(onAddIssue).toHaveBeenCalled()
    expect(screen.getByText('No JQL needed')).toBeVisible()
  })

  it('surfaces ticket write-back failures and blocks numeric write-back for T-shirt rooms', () => {
    render(<JiraWritebackPanel
      connection={{ jira_display_name: 'Maya' }}
      tickets={[{
        id: 'ticket-1', issue_key: 'PAY-1', jira_issue_id: '101',
        final_estimate: 'M', final_assignee_display_name: null,
        jira_writeback_error: 'Jira unavailable',
      }]}
      scale="tshirt"
      result={{ succeeded_count: 0, failed_count: 1 }}
      writing={false}
      onWriteback={vi.fn()}
    />)

    expect(screen.getByText(/PAY-1: Jira unavailable/)).toBeVisible()
    expect(screen.getByRole('button', { name: /Write final results to Jira/ })).toBeDisabled()
    expect(screen.getByText(/T-shirt estimates cannot be written/)).toBeVisible()
    expect(screen.getByText('0 updated · 1 failed')).toBeVisible()
  })
})
