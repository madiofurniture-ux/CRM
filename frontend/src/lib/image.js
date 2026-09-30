/**
 * Shrink a captured photo to a small JPEG data URL before it is stored.
 *
 * Site photos come straight off a phone camera at 3–8 MB. Storing those raw
 * would blow past MongoDB's 16 MB document limit within a few shots and make
 * every survey load painfully slow over mobile data. We downscale to a long
 * edge of ~900px and re-encode as JPEG, which keeps a window/door opening
 * perfectly legible at roughly 60–120 KB.
 */
export function shrinkImage(file, maxPx = 900, quality = 0.72) {
  return new Promise((resolve, reject) => {
    if (!file) return reject(new Error("No file"));
    if (!/^image\//.test(file.type)) return reject(new Error("Not an image"));

    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read that file"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("Could not decode that image"));
      img.onload = () => {
        let { width: w, height: h } = img;
        if (w > maxPx || h > maxPx) {
          const scale = maxPx / Math.max(w, h);
          w = Math.round(w * scale);
          h = Math.round(h * scale);
        }
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        // white matte: JPEG has no alpha, and PNGs with transparency would
        // otherwise composite onto black.
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, w, h);
        ctx.drawImage(img, 0, 0, w, h);

        let out = canvas.toDataURL("image/jpeg", quality);
        // Very large originals can still land big; step down once more.
        if (out.length > 400_000) out = canvas.toDataURL("image/jpeg", 0.55);
        resolve(out);
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

/** Rough decoded size of a data URL, for showing the user what they're storing. */
export function dataUrlKb(dataUrl) {
  if (!dataUrl) return 0;
  const b64 = String(dataUrl).split(",")[1] || "";
  return Math.round((b64.length * 3) / 4 / 1024);
}
