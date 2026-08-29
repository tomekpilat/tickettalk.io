export function JiraConnectForm({ draft, setDraft, connecting, onConnect }) {
  return (
    <form className="panel jira-connect" onSubmit={onConnect}>
      <div className="panel-label"><span>Room-scoped Jira connection</span><small>Private</small></div>
      <p className="settings-note">Use an API token from your Jira account. It is encrypted by the API and never sent to other room members.</p>
      <label>Jira site URL<input aria-label="Jira site URL" required placeholder="https://company.atlassian.net" value={draft.site_url} onChange={(event) => setDraft({ ...draft, site_url: event.target.value })} /></label>
      <label>Jira email<input aria-label="Jira email" type="email" required value={draft.email} onChange={(event) => setDraft({ ...draft, email: event.target.value })} /></label>
      <label>API token<input aria-label="Jira API token" type="password" required autoComplete="off" value={draft.api_token} onChange={(event) => setDraft({ ...draft, api_token: event.target.value })} /></label>
      <button className="primary" disabled={connecting}>{connecting ? 'Connecting…' : 'Connect Jira'}</button>
    </form>
  )
}

export function JiraImportPanel({
  connection,
  jql,
  setJql,
  duplicateBehavior,
  setDuplicateBehavior,
  preview,
  searching,
  importing,
  onSelectField,
  onDisconnect,
  onSearch,
  onImport,
}) {
  return (
    <>
      <div className="jira-connected">
        <span><i /> Connected to <strong>{connection.site_url}</strong> as {connection.jira_display_name}</span>
        {connection.story_points_fields?.length > 0 && (
          <label>Estimate field<select aria-label="Jira estimate field" value={connection.story_points_field_id || ''} onChange={(event) => onSelectField(event.target.value)}>{connection.story_points_fields.map((field) => <option value={field.id} key={field.id}>{field.name}</option>)}</select></label>
        )}
        <button className="secondary" onClick={onDisconnect}>Disconnect</button>
      </div>
      <section className="import-grid">
        <div className="panel import-editor">
          <div className="panel-label"><span>JQL query</span><small>01</small></div>
          <textarea aria-label="JQL query" value={jql} onChange={(event) => setJql(event.target.value)} />
          <label className="duplicate-choice">Existing Jira keys<select value={duplicateBehavior} onChange={(event) => setDuplicateBehavior(event.target.value)}><option value="error">Ask me to decide</option><option value="skip">Skip existing</option><option value="replace">Refresh existing</option></select></label>
          <div className="editor-actions"><button className="primary" disabled={searching || !jql.trim()} onClick={onSearch}>{searching ? 'Running JQL…' : 'Preview tickets'}</button><span>Maximum 500 tickets</span></div>
        </div>
        <div className="panel preview">
          <div className="panel-label"><span>Jira preview</span><small>{String(preview?.source_count || 0).padStart(2, '0')}</small></div>
          {searching && <p className="preview-message">Querying Jira…</p>}
          {preview?.errors.map((error) => <div className="import-error" key={`${error.row_number}-${error.field}`}><strong>{error.field}</strong><span>{error.message}</span><small>{error.fix}</small></div>)}
          {!searching && preview?.rows.map((item) => <div className="preview-row" key={item.jira_issue_id}><span>{item.issue_key}</span><p>{item.summary}</p><small>{item.action}</small></div>)}
          {!preview && !searching && <p className="preview-message">Run the query to review exactly what will be imported.</p>}
          <div className="preview-counts"><span>{preview?.saved_count || 0} to save</span><span>{preview?.skipped_count || 0} skipped</span></div>
          <button className="primary wide" disabled={searching || importing || !preview?.saved_count || preview.errors.length > 0} onClick={onImport}>{importing ? 'Importing from Jira…' : `Import ${preview?.saved_count || 0} tickets`} <span>→</span></button>
        </div>
      </section>
    </>
  )
}

export function JiraWritebackPanel({
  connection,
  tickets,
  scale,
  result,
  writing,
  onWriteback,
}) {
  const jiraTickets = tickets.filter((ticket) => ticket.jira_issue_id)
  const incomplete = jiraTickets.some((ticket) => ticket.final_estimate == null)
  const written = jiraTickets.filter((ticket) => ticket.jira_writeback_at).length
  const failed = jiraTickets.filter((ticket) => ticket.jira_writeback_error)
  return (
    <section className="panel jira-writeback">
      <div className="panel-label"><span>Jira write-back</span><small>{connection?.jira_display_name || 'Connected account'}</small></div>
      <p>When ownership and pricing look right, write both fields to Jira in one confirmed action.</p>
      <div className="jira-writeback-overview"><span><strong>{jiraTickets.length}</strong> Jira tickets</span><span><strong>{written}</strong> written</span><span className={failed.length ? 'write-failed' : ''}><strong>{failed.length}</strong> failed</span></div>
      {failed.map((ticket) => <p className="form-error" key={ticket.id}>{ticket.issue_key}: {ticket.jira_writeback_error}</p>)}
      {result && <div className={result.failed_count ? 'writeback-result failed' : 'writeback-result'}>{result.succeeded_count} updated · {result.failed_count} failed</div>}
      <button className="primary" disabled={writing || scale === 'tshirt' || incomplete} onClick={onWriteback}>{writing ? 'Writing to Jira…' : 'Write final results to Jira'} <span>→</span></button>
      {scale === 'tshirt' && <p className="form-error">T-shirt estimates cannot be written to Jira’s numeric Story Points field.</p>}
    </section>
  )
}
