import { formatProperty, requirementStatusLabel, type RenderManifest } from '../lib/model';

const COMPARISONS = { atLeast: 'at least', atMost: 'at most', equals: 'equal to' };

export default function DesignRequirements({ manifest }: { manifest: RenderManifest }) {
  if (!manifest.requirements?.length) return null;
  return (
    <details className="project-requirements">
      <summary>Design requirements ({manifest.requirements.length})</summary>
      {manifest.requirements.map((requirement) => {
        const result = manifest.requirementResults?.find((entry) => entry.id === requirement.id);
        return (
          <div className="requirement-entry" key={requirement.id}>
            <span className={`requirement-status requirement-${result?.status ?? 'unknown'}`}>{requirementStatusLabel(result)}</span>
            <p>{requirement.statement}</p>
            <small>{requirement.check ? 'Violation severity' : 'Note level'}: {requirement.severity}</small>
            {!!requirement.appliesTo?.length && <small>Applies to: {requirement.appliesTo.map((id) => manifest.elements[id]?.name ?? id).join(', ')}</small>}
            {result?.checks.map((check) => (
              <small className="requirement-measurement" key={check.elementId}>
                {manifest.elements[check.elementId]?.name ?? check.elementId}: {check.property.replace(/([A-Z])/g, ' $1').toLowerCase()}
                {' — '}{formatProperty(check.property, check.actual) ?? 'unavailable'}
                {'; required '}{COMPARISONS[check.operator]} {formatProperty(check.property, check.expected)}
                {'. '}{check.status === 'satisfied' ? 'Satisfied' : 'Violated'}.
              </small>
            ))}
          </div>
        );
      })}
    </details>
  );
}
