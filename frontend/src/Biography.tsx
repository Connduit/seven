export type Biography = {
  birthdate: string | null;
  birthplace: string;
  current_location: string;
  pronouns: string;
  occupation: string;
  background: string;
  appearance: string;
};
export const emptyBiography: Biography = { birthdate: '', birthplace: '', current_location: '', pronouns: '', occupation: '', background: '', appearance: '' };
const fields = [
  ['birthplace', 'Birthplace', 'e.g. Portland, Oregon, USA'],
  ['current_location', 'Current location', 'e.g. Lisbon, Portugal'],
  ['pronouns', 'Pronouns', 'e.g. she/her'],
  ['occupation', 'Occupation', 'e.g. Photographer and travel writer'],
  ['background', 'Background & life story', 'Family, upbringing, education, and defining experiences…'],
  ['appearance', 'Appearance', 'Established hair, eyes, style, and other visual details…'],
] as const;
function today() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
}
export function BiographyFields({ value, onChange }: { value: Biography; onChange: (value: Biography) => void }) {
  return <fieldset className="biography-fields"><legend>Fictional biography</legend><small>Optional character details to keep their story consistent.</small><label>Birthdate<input type="date" max={today()} value={value.birthdate || ''} onChange={e => onChange({...value, birthdate:e.target.value})}/></label>{fields.map(([key, title, placeholder]) => <label key={key}>{title}<textarea rows={key === 'background' || key === 'appearance' ? 3 : 1} maxLength={key === 'background' ? 10000 : key === 'appearance' ? 3000 : key === 'pronouns' ? 100 : 200} value={value[key]} placeholder={placeholder} onChange={e => onChange({...value, [key]:e.target.value})}/></label>)}</fieldset>;
}
export function BiographyDetails({ value }: { value: Biography }) {
  let age: number | null = null;
  let birthday = 'Not set';
  if (value.birthdate) {
    const [year, month, day] = value.birthdate.split('-').map(Number);
    const now = new Date();
    age = now.getFullYear()-year-Number(now.getMonth()+1 < month || (now.getMonth()+1 === month && now.getDate() < day));
    // Format calendar dates directly to avoid UTC/local birthday shifts.
    const date = new Date(0); date.setFullYear(year, month-1, day);
    birthday = date.toLocaleDateString(undefined, { year:'numeric', month:'long', day:'numeric' });
  }
  return <section className="biography-details"><h3>Fictional biography</h3><dl className="profile-details"><dt>Birthdate</dt><dd>{birthday}{age !== null && ` · ${age} years old`}</dd>{fields.map(([key, title]) => <div key={key}><dt>{title}</dt><dd>{value[key] || 'Not set'}</dd></div>)}</dl></section>;
}
