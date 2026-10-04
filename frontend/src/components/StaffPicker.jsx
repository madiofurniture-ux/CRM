import { useEffect, useMemo, useState } from "react";
import SearchSelect from "@/components/SearchSelect";
import api from "@/lib/api";

// One fetch of the team list per page load, shared by every picker on screen.
let _staff = null;
const loadStaff = () => {
  if (!_staff) {
    _staff = api.get("/users/directory").then(({ data }) => data || []).catch(() => {
      _staff = null;
      return [];
    });
  }
  return _staff;
};

/**
 * Pick a team member for "Handled by", "Assigned to", "Engineer"… fields.
 * These fields store the person's display name (the convention across the
 * CRM), so `value` and `onChange(name, user)` are names; a saved name that
 * isn't a current user (older records) still shows and can be kept.
 */
export default function StaffPicker({ value = "", onChange, placeholder = "Pick a team member…", testId }) {
  const [staff, setStaff] = useState([]);
  useEffect(() => { let live = true; loadStaff().then((s) => live && setStaff(s)); return () => { live = false; }; }, []);

  const options = useMemo(() => {
    // People only: shared role logins and deactivated staff aren't offered.
    const opts = staff.filter((u) => u.name && !u.shared_login && u.active !== false)
      .map((u) => ({ id: u.name, label: u.name, user: u }))
      .sort((a, b) => a.label.localeCompare(b.label));
    if (value && !opts.some((o) => o.id === value)) opts.unshift({ id: value, label: value, sub: "not a current staff member" });
    return opts;
  }, [staff, value]);

  return (
    <SearchSelect
      options={options}
      value={value || ""}
      onChange={(id, opt) => onChange?.(id || "", opt?.user || null)}
      placeholder={placeholder}
      emptyLabel="No team member found"
      testId={testId}
    />
  );
}
