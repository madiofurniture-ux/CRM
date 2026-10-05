import usePicklists from "@/hooks/usePicklists";

/** A dropdown fed by a Master Data list. `placeholder` is the empty choice
 * ("—" by default); pass required to leave it out. */
export default function PicklistSelect({ list, value = "", onChange, placeholder = "—", required = false,
                                         className = "", testId, ariaLabel }) {
  const { values } = usePicklists();
  const opts = values(list, value);
  return (
    <select value={value || ""} onChange={(e) => onChange?.(e.target.value)} className={className}
            data-testid={testId} aria-label={ariaLabel}>
      {!required && <option value="">{placeholder}</option>}
      {required && !value && <option value="" disabled>{placeholder}</option>}
      {opts.map((v) => <option key={v} value={v}>{v}</option>)}
    </select>
  );
}
