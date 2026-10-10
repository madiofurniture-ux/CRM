import { useEffect, useState } from "react";
import api from "@/lib/api";

let known = null;

/** Brand names per division (for messages to customers) and, for people who
 * can see landing prices, the markup vendor prices are imported at. */
export default function useCatalogueMeta() {
  const [meta, setMeta] = useState(known || { brands: {} });
  useEffect(() => {
    let live = true;
    api.get("/virtual-items/meta").then(({ data }) => {
      known = data || known;
      if (live && data) setMeta(data);
    }).catch(() => {});
    return () => { live = false; };
  }, []);
  return meta;
}
