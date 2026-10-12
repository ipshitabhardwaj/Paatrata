import React, { useEffect, useState } from "react";

// Real photographs, only when they have been downloaded with their credits
// (python web/scripts/get_photos.py). Without them this section is not rendered.
export function usePhotos() {
  const [photos, setPhotos] = useState([]);
  useEffect(() => {
    fetch("/photos/photos.json")
      .then((r) => (r.ok ? r.json() : []))
      .then((p) => setPhotos(Array.isArray(p) ? p : []))
      .catch(() => setPhotos([]));
  }, []);
  return photos;
}

function Credit({ p }) {
  return (
    <span className="credit">
      {p.caption}. Photo: {p.author},{" "}
      <a href={p.license_url || p.source} target="_blank" rel="noreferrer">
        {p.license}
      </a>
      , via{" "}
      <a href={p.source} target="_blank" rel="noreferrer">
        Wikimedia Commons
      </a>
    </span>
  );
}

export default function PhotoBand({ photos }) {
  if (!photos.length) return null;
  const [lead, ...rest] = photos;
  return (
    <section className="photos" aria-label="Chandigarh">
      <figure className="photo-lead">
        <img src={lead.file} alt={lead.caption} loading="lazy" style={{ objectPosition: lead.focus || "50% 50%" }} />
        <figcaption>
          <h2>Built for Chandigarh first</h2>
          <p>
            The Union Territory runs its own pensions and child-support schemes next to the central ones, so one resident faces two
            rulebooks. Paatrata starts with Chandigarh's, and reads any state's notifications the same way.
          </p>
          <Credit p={lead} />
        </figcaption>
      </figure>
      {rest.length > 0 && (
        <div className="photo-row">
          {rest.slice(0, 4).map((p) => (
            <figure key={p.slug}>
              <img src={p.file} alt={p.caption} loading="lazy" />
              <figcaption>
                <Credit p={p} />
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </section>
  );
}
