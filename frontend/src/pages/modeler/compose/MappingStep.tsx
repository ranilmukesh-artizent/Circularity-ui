import { useState } from 'react';
import { markStep, useComposeSystems, type ComposeSystem, type Composition } from '../../../api/compose';
import { Modal } from '../../../components/Overlay';
import { StatusPill } from '../../../components/kit/StatusPill';
import { toast } from '../../../components/toast';
import { useAction } from '../../../hooks/useAction';
import { MappingSuggestions } from '../../integration/MappingSuggestions';
import { RegistryPicker } from '../../integration/RegistryPicker';
import { TestRunCard } from './TestRunCard';
import { canMarkMappingDone, needsAdapter, statusLabel, statusTone, summaryLine, totalMapping } from './composeView';

/**
 * Step 2 of Compose (plan 9, P9-8.18, story X-10): one row per system the changes need, with how far it is connected. A system
 * with no source offers "Add from the adapter registry" (the registry picker; a new connection starts in test and its system
 * owner approves production). A system with a source opens the suggested mappings in place, where each field is the person's
 * choice. "Mark done" waits while a field waits for its system owner.
 */
export function MappingStep({ c }: { c: Composition }) {
  const systems = useComposeSystems(c.id);
  const [adding, setAdding] = useState<ComposeSystem | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const action = useAction();
  const editable = c.status === 'draft' || c.status === 'sent_back';
  const done = c.steps.mapping.state === 'done';
  const waiting = totalMapping(systems).asked_owner;
  const lacking = needsAdapter(systems);

  const mark = async () => {
    const r = await action.run(() => markStep(c.id, 'mapping'));
    if (r.ok) toast('The adapter mapping step is done.');
  };

  return (
    <div className="cmp-step">
      <p className="note">Each system the changes need must be connected before the owner can approve. A new connection runs in the test environment, read only.</p>
      <table className="t static" aria-label="Systems">
        <thead><tr><th>System</th><th>Status</th><th>Source</th><th>Mapping</th><th /></tr></thead>
        <tbody>
          {systems.map((x) => (
            <tr key={x.name}>
              <td><b>{x.name}</b><div className="note">{x.system_type}</div></td>
              <td><StatusPill tone={statusTone(x.status)} label={statusLabel(x.status)} /></td>
              <td>{x.source_id ?? 'none'}</td>
              <td className="note">{x.source_id ? summaryLine(x.mapping) : 'Connect it first'}</td>
              <td>
                {x.status === 'needs_adapter' && editable && <button className="btn sm" onClick={() => setAdding(x)}>Add from the adapter registry</button>}
                {x.source_id && <button className="btn sm" aria-expanded={open === x.source_id} onClick={() => setOpen(open === x.source_id ? null : x.source_id)}>{open === x.source_id ? 'Hide mappings' : 'Review mappings'}</button>}
              </td>
            </tr>
          ))}
          {systems.length === 0 && <tr><td colSpan={5} className="note">The changes name no system.</td></tr>}
        </tbody>
      </table>
      {open && (
        <div className="cmp-inline">
          <h4>Suggested mappings for {open}</h4>
          <MappingSuggestions sourceId={open} />
        </div>
      )}
      {editable && (
        <div className="row">
          <button className="btn sm pri" disabled={action.pending || done || !canMarkMappingDone(systems)} onClick={() => void mark()}>{done ? 'Done' : 'Mark done'}</button>
          {waiting > 0 && <span className="note">Waiting for the system owner on {waiting} field{waiting === 1 ? '' : 's'}.</span>}
          {waiting === 0 && lacking.length > 0 && !done && <span className="note">Still without an adapter: {lacking.join(', ')}. You may mark the step done once you accept that.</span>}
        </div>
      )}
      <TestRunCard c={c} />
      {adding && (
        <Modal title={'Add ' + adding.name} wide onClose={() => setAdding(null)}>
          <p className="note">System type: <b>{adding.system_type}</b>. {adding.registry.length > 0 ? `Registry entries of this type: ${adding.registry.join(', ')}.` : 'No registry entry has this type yet: use Generic REST or draft one from an API spec.'}</p>
          <RegistryPicker onClose={() => setAdding(null)} onCreated={() => setAdding(null)} />
        </Modal>
      )}
    </div>
  );
}
